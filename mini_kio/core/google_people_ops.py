"""Google People API (contacts) — via the existing Google OAuth credential.

KIO owns the contacts capability; Google owns the external implementation.
Uses the same OAuth client/account and the centralized scope registry
(`google_oauth.GOOGLE_SCOPES["contacts"]`). No second OAuth identity.

Scope note: the `contacts` scope must be present on the stored grant. It is
requested through `google_oauth.ACTIVE_SCOPES`; a credential authorized before
People was added will report a scope error until it is re-consented once —
KIO surfaces that as a distinct reason instead of a generic failure.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

BACKEND = "google_people"

_PERSON_FIELDS = "names,emailAddresses,phoneNumbers,biographies,organizations,metadata"
_WRITE_FIELDS = "names,emailAddresses,phoneNumbers,biographies"


def _service():
    from mini_kio.core.google_oauth import get_people_service
    return get_people_service()


def _person_summary(person: dict[str, Any]) -> dict[str, Any]:
    names = person.get("names") or []
    emails = person.get("emailAddresses") or []
    phones = person.get("phoneNumbers") or []
    bios = person.get("biographies") or []
    orgs = person.get("organizations") or []
    return {
        "resource_name": person.get("resourceName", ""),
        "display_name": (names[0].get("displayName", "") if names else ""),
        "given_name": (names[0].get("givenName", "") if names else ""),
        "family_name": (names[0].get("familyName", "") if names else ""),
        "emails": [e.get("value", "") for e in emails],
        "phones": [p.get("value", "") for p in phones],
        "notes": (bios[0].get("value", "") if bios else ""),
        "organization": (orgs[0].get("name", "") if orgs else ""),
    }


def _scope_error(exc: Exception) -> str:
    """Distinguish 'scope not granted yet' from a real API failure."""
    text = str(exc)
    if "insufficient" in text.lower() or "PERMISSION_DENIED" in text or "403" in text:
        return (
            "Google People API scope not granted on the stored credential — "
            "run the OAuth consent once to add the contacts scope "
            "(existing client/credential; no new OAuth identity). "
            f"Detail: {text[:200]}"
        )
    return f"Google People API failed: {text[:300]}"


def list_contacts(page_size: int = 25, page_token: str = "") -> dict[str, Any]:
    """List the authorized account's contacts (connections)."""
    try:
        service = _service()
        params: dict[str, Any] = {
            "resourceName": "people/me",
            "pageSize": int(page_size),
            "personFields": _PERSON_FIELDS,
        }
        if page_token:
            params["pageToken"] = page_token
        result = service.people().connections().list(**params).execute()
        contacts = [_person_summary(p) for p in result.get("connections", [])]
        return {"success": True, "contacts": contacts, "count": len(contacts),
                "next_page_token": result.get("nextPageToken", ""), "backend": BACKEND,
                "message": f"{len(contacts)} contacts from Google People API"}
    except Exception as exc:
        logger.warning("[GOOGLE_PEOPLE] list_contacts failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def search_contacts(query: str, page_size: int = 25) -> dict[str, Any]:
    """Search contacts by name/email/phone substring."""
    if not query:
        return {"success": False, "message": "search_contacts: missing query"}
    try:
        service = _service()
        result = service.people().searchContacts(
            query=query, pageSize=int(page_size), readMask=_PERSON_FIELDS,
        ).execute()
        contacts = []
        for entry in result.get("results", []):
            person = entry.get("person") or {}
            if person:
                contacts.append(_person_summary(person))
        return {"success": True, "contacts": contacts, "count": len(contacts),
                "query": query, "backend": BACKEND,
                "message": f"{len(contacts)} contacts matching '{query}'"}
    except Exception as exc:
        logger.warning("[GOOGLE_PEOPLE] search_contacts failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def get_contact(resource_name: str) -> dict[str, Any]:
    """Fetch one contact by resource name (e.g. people/c123...)."""
    if not resource_name:
        return {"success": False, "message": "get_contact: missing resource_name"}
    try:
        service = _service()
        person = service.people().get(resourceName=resource_name,
                                      personFields=_PERSON_FIELDS).execute()
        return {"success": True, "contact": _person_summary(person), "backend": BACKEND,
                "message": f"Contact {person.get('resourceName', resource_name)}"}
    except Exception as exc:
        logger.warning("[GOOGLE_PEOPLE] get_contact failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def _build_body(given_name: str, family_name: str, email: str,
                phone: str, notes: str) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if given_name or family_name:
        body["names"] = [{"givenName": given_name or "", "familyName": family_name or ""}]
    if email:
        body["emailAddresses"] = [{"value": email}]
    if phone:
        body["phoneNumbers"] = [{"value": phone}]
    if notes:
        body["biographies"] = [{"value": notes, "contentType": "TEXT_PLAIN"}]
    return body


def create_contact(given_name: str = "", family_name: str = "", email: str = "",
                   phone: str = "", notes: str = "") -> dict[str, Any]:
    """Create a contact."""
    body = _build_body(given_name, family_name, email, phone, notes)
    if not body:
        return {"success": False, "message": "create_contact: no contact fields supplied"}
    try:
        service = _service()
        person = service.people().createContact(body=body).execute()
        return {"success": True, "contact": _person_summary(person),
                "resource_name": person.get("resourceName", ""), "backend": BACKEND,
                "message": f"Created contact {(given_name + ' ' + family_name).strip() or email}"}
    except Exception as exc:
        logger.warning("[GOOGLE_PEOPLE] create_contact failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def update_contact(resource_name: str, given_name: str = "", family_name: str = "",
                   email: str = "", phone: str = "", notes: str = "") -> dict[str, Any]:
    """Update a contact. Reads the current etag first, as the API requires."""
    if not resource_name:
        return {"success": False, "message": "update_contact: missing resource_name"}
    body = _build_body(given_name, family_name, email, phone, notes)
    if not body:
        return {"success": False, "message": "update_contact: no updatable fields supplied"}
    try:
        service = _service()
        current = service.people().get(resourceName=resource_name,
                                       personFields="metadata").execute()
        body["etag"] = current.get("etag", "")
        fields = ",".join(sorted(body.keys() - {"etag"}))
        person = service.people().updateContact(
            resourceName=resource_name, updatePersonFields=fields, body=body,
        ).execute()
        return {"success": True, "contact": _person_summary(person), "backend": BACKEND,
                "message": f"Updated contact {resource_name}"}
    except Exception as exc:
        logger.warning("[GOOGLE_PEOPLE] update_contact failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def delete_contact(resource_name: str) -> dict[str, Any]:
    """Delete a contact."""
    if not resource_name:
        return {"success": False, "message": "delete_contact: missing resource_name"}
    try:
        service = _service()
        service.people().deleteContact(resourceName=resource_name).execute()
        return {"success": True, "deleted": resource_name, "backend": BACKEND,
                "message": f"Deleted contact {resource_name}"}
    except Exception as exc:
        logger.warning("[GOOGLE_PEOPLE] delete_contact failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


GOOGLE_PEOPLE_ACTIONS: dict[str, Any] = {
    "list_contacts": list_contacts,
    "search_contacts": search_contacts,
    "get_contact": get_contact,
    "create_contact": create_contact,
    "update_contact": update_contact,
    "delete_contact": delete_contact,
}

__all__ = list(GOOGLE_PEOPLE_ACTIONS) + ["BACKEND", "GOOGLE_PEOPLE_ACTIONS"]
