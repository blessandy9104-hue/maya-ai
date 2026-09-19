"""Role directives bound to the registered market roles and their domains."""

ROLES = (
    "ai_companion",
    "customer_service_agent",
    "educational_tutor",
    "enterprise_assistant",
    "holographic_assistant",
    "robotics_interface",
    "therapy_support_agent",
    "vtuber_avatar",
)

ROLE_DOMAINS = {
    "educational_tutor": "tutoring",
    "customer_service_agent": "customer_service",
    "therapy_support_agent": "therapy_support",
    "robotics_interface": "robotics_interface",
    "ai_companion": "entertainment",
    "vtuber_avatar": "entertainment",
    "holographic_assistant": None,
    "enterprise_assistant": None,
}

ROLE_DIRECTIVES = {
    "educational_tutor": {
        "domain": "tutoring",
        "directives": (
            "scaffold and verify progress",
            "never solve silently",
            "keep pace adaptive",
        ),
        "safe_override": "return neutral guidance with a next step",
    },
    "customer_service_agent": {
        "domain": "customer_service",
        "directives": (
            "state options and follow policy",
            "escalate to a representative when needed",
            "never invent policy",
        ),
        "safe_override": "escalate to a representative",
    },
    "therapy_support_agent": {
        "domain": "therapy_support",
        "directives": (
            "reflect and validate only",
            "never diagnose or direct",
            "flag crisis paths to safety monitor",
            "low-amplitude, de-escalation-only motion",
        ),
        "safe_override": "return supportive neutral wording; flag for human support",
    },
    "robotics_interface": {
        "domain": "robotics_interface",
        "directives": (
            "metric-first vocabulary",
            "report bounds honestly",
            "command only what is math-approved",
        ),
        "safe_override": "cease command and report the bound",
    },
    "ai_companion": {
        "domain": "entertainment",
        "directives": (
            "companionship within safe limits",
            "playful but never harmful",
            "no deceptive content",
        ),
        "safe_override": "return warm neutral wording",
    },
    "vtuber_avatar": {
        "domain": "entertainment",
        "directives": (
            "streaming-suitable expression",
            "bounded performance energy",
            "brand-accented presentation",
        ),
        "safe_override": "return lively neutral wording",
    },
    "holographic_assistant": {
        "domain": None,
        "directives": (
            "neutral even tone",
            "business_clear vocabulary",
            "no role-owned domain behavior",
        ),
        "safe_override": "return even neutral wording",
    },
    "enterprise_assistant": {
        "domain": None,
        "directives": (
            "clear and cautious wording",
            "enterprise-policy-abiding",
            "no brand mutation",
        ),
        "safe_override": "return clear neutral wording",
    },
}


def roles():
    """Sorted tuple of registered role ids."""
    return ROLES


def domain_for(role):
    """Domain string (or None) for a role; unknown ids raise ValueError."""
    if role not in ROLE_DIRECTIVES:
        raise ValueError("unknown role: %s" % role)
    return ROLE_DOMAINS[role]


def directives_for(role):
    """Tuple of directive rules for a role."""
    if role not in ROLE_DIRECTIVES:
        raise ValueError("unknown role: %s" % role)
    return ROLE_DIRECTIVES[role]["directives"]


def safe_override_for(role):
    """Fail-closed branch text for a role."""
    if role not in ROLE_DIRECTIVES:
        raise ValueError("unknown role: %s" % role)
    return ROLE_DIRECTIVES[role]["safe_override"]


def validate_directives():
    """Registry-level invariants over role directives."""
    for role in ROLES:
        if role not in ROLE_DIRECTIVES:
            raise ValueError("role missing directives: %s" % role)
        entry = ROLE_DIRECTIVES[role]
        if not (entry["directives"] and entry["safe_override"]):
            raise ValueError("empty directives for role: %s" % role)
        for role_id in ROLE_DOMAINS:
            if role_id not in ROLE_DIRECTIVES:
                raise ValueError("role missing domain entry: %s" % role_id)