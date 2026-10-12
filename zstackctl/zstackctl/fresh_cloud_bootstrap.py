"""Pure admission rules for the installer-only fresh Cloud bootstrap option."""


def validate_fresh_cloud_bootstrap(drop, keep_db, database_check_succeeded, schema_exists):
    if drop or keep_db:
        raise ValueError("fresh-cloud bootstrap cannot be combined with drop/keep database modes")
    if not database_check_succeeded:
        raise ValueError("target database absence could not be verified")
    if schema_exists:
        raise ValueError("target zstack database already exists")
    return True
