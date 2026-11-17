"""Checklist helpers for Flyover's "Before you go" preview and Checklist tab (guide pages 3–4).

Pure functions over the API's workflow data, no Streamlit, so they are easy to test:
- document_groups: the selected task's documents, then each prerequisite's own documents;
- fact_sources: the evidence behind one visit fact (citation field + text, joined to sources);
- task_actions: the link to the action a student can take, labelled by its real destination.

Nothing here invents a URL, an hour or a verification state. An action link only comes from a
URL the API already sends for this task (its school-scoped sources or before_you_go), so a
CRC link never reaches a student at another school.
"""

import re

from .frontend import safe_url

# Sources whose page *is* the place to act, in order of preference, with an honest label for
# what that page is. A task gets one only when the API cites that rule for the task.
# rule_dmv_real_id_booking: DMV's "Schedule an Appointment" page (checked 2026-11-17).
# rule_california_real_id_residency: the interactive "REAL ID Checklist" page (checked 2026-11-17).
# rule_crc_fall_2026_payment_deadline: CRC's fee payment deadlines page (the verified rule). A
# direct payment link isn't in the rules yet and couldn't be checked here (ENG proposal).
# A rule only becomes an action if the task cites it, which keeps CRC links CRC-only.
ACTION_SOURCES = (
    ('rule_dmv_real_id_booking', 'Schedule a DMV visit',
     'California DMV appointments page. Booking is on DMV’s site; Flyover books nothing.'),
    ('rule_california_real_id_residency', 'Open the REAL ID document checklist',
     'DMV’s interactive checklist. This step is preparation for the DMV visit.'),
    ('rule_crc_fall_2026_payment_deadline', 'Open CRC fee payment instructions',
     'CRC’s fee payment deadlines page. A direct payment link isn’t on file yet.'),
)
PHONE = re.compile(r'^\(?(\d{3})\)?[\s.-]*(\d{3})[\s.-]*(\d{4})$')


def _documents(task: dict) -> list[str]:
    # dict.fromkeys: a document listed twice for one task shows once, in its first position.
    return list(dict.fromkeys((task.get('before_you_go') or {}).get('required_documents') or []))


def document_groups(task: dict, by_id: dict) -> list[dict]:
    """[{task, documents, shared}] for the task, then one group per prerequisite in the API.

    A document needed by two of these tasks stays under both; `shared` maps it to the titles of
    the other tasks in the preview that also need it, so the connection stays visible.
    """
    tasks = [task] + [by_id[key] for key in task.get('prerequisites') or [] if key in by_id]
    lists = {item['id']: _documents(item) for item in tasks}
    groups = []
    for item in tasks:
        shared = {doc: [other['title'] for other in tasks
                        if other['id'] != item['id'] and doc in lists[other['id']]]
                  for doc in lists[item['id']]}
        groups.append({'task': item, 'documents': lists[item['id']],
                       'shared': {doc: titles for doc, titles in shared.items() if titles}})
    return groups


def fact_sources(task: dict, field: str) -> list[dict] | None:
    """The sources behind one before_you_go fact, or None when nothing cites it.

    A citation counts only when both its field and its text match the fact shown, so a stale
    citation can't vouch for different words. Its rule_id is joined to task['sources'] for the
    URL and date; a cited rule missing from the sources becomes a URL-less entry that keeps the
    citation's own verification state.
    """
    guide = task.get('before_you_go') or {}
    value = guide.get(field)
    cited = [c for c in guide.get('citations') or []
             if c.get('field') == field and c.get('text') == value]
    if not cited:
        return None
    by_rule = {s.get('rule_id'): s for s in task.get('sources') or []}
    found = []
    for citation in cited:
        found.append(by_rule.get(citation['rule_id']) or {
            'rule_id': citation['rule_id'], 'url': None, 'last_verified': None,
            'verification_status': citation.get('verification_status')})
    return list({s['rule_id']: s for s in found}.values())  # one row per rule


def phone_link(text: str | None) -> str | None:
    """'tel:+19166917411' for a single US phone number, else None (several numbers or prose)."""
    match = PHONE.match((text or '').strip())
    return 'tel:+1' + ''.join(match.groups()) if match else None


def task_actions(task: dict, page_name=lambda url: url) -> list[dict]:
    """[{label, url, note}]: links to where the student acts, each labelled by its destination.

    Order: the preferred action page the API cites for this task; a phone number when the
    task's appointment guidance and phone come from the same source (that office takes
    appointments by phone); then the task's own official_url if it is a different page,
    labelled with page_name(url) (the page's own name, never a guessed purpose).
    """
    guide = task.get('before_you_go') or {}
    sources = {s.get('rule_id'): s for s in task.get('sources') or []}
    actions: list[dict] = []
    for rule_id, label, note in ACTION_SOURCES:
        if rule_id in sources and (url := safe_url(sources[rule_id].get('url'))):
            actions.append({'label': label, 'url': url, 'note': note})
            break
    citations = {c.get('field'): c.get('rule_id') for c in guide.get('citations') or []}
    tel = phone_link(guide.get('phone'))
    if tel and citations.get('phone') and citations.get('phone') == citations.get(
            'appointment_rules'):
        actions.append({'label': f'Call to schedule: {guide["phone"]}', 'url': tel,
                        'note': 'The office takes appointment requests by phone.'})
    official = safe_url(guide.get('official_url'))
    if official and official not in {action['url'] for action in actions}:
        actions.append({'label': 'Open ' + page_name(official), 'url': official,
                        'note': None})
    return actions
