"""
DefectDojo missing "basic" attributes used by IDCS - so we don't have to use DD_SAML2_ALLOW_UNKNOWN_ATTRIBUTE=true

As per https://djangosaml2.readthedocs.io/contents/setup.html#attribute-map:
This is a copy of https://github.com/IdentityPython/pysaml2/blob/7cb4f09dce87a7e8098b9c7552ebab8bc77bc896/src/saml2/attributemaps/basic.py
And the modified just for our IDCS mapping
"""

DEF = ""

MAP = {
    "identifier": "urn:oasis:names:tc:SAML:2.0:attrname-format:basic",
    "fro": {
        f"{DEF}email": "Email",
        f"{DEF}firstName": "Firstname",
        f"{DEF}lastName": "Lastname",
        f"{DEF}username": "UserName",
        f"{DEF}groups": "groups",
        "oracle:cloud:identity:url": "ociURL",
        "oracle:cloud:identity:tenant": "ociTenant",
        "oracle:cloud:identity:sessionid": "ociSessionID",
        "oracle:cloud:identity:domain": "ociDomain",
    },
    "to": {
        "Email": f"{DEF}email",
        "Firstname": f"{DEF}firstName",
        "Lastname": f"{DEF}lastName",
        "UserName": f"{DEF}username",
        "groups": f"{DEF}groups",
        "ociURL": "oracle:cloud:identity:url",
        "ociTenant": "oracle:cloud:identity:tenant",
        "ociSessionID": "oracle:cloud:identity:sessionid",
        "ociDomain": "oracle:cloud:identity:domain",
    },
}