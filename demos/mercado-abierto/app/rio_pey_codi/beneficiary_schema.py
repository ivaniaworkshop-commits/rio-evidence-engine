"""Ordinary mutation guards; database administrators can alter these guards."""


def install_claim_guards(connection):
    if connection.dialect.name == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            connection.exec_driver_sql(f"""CREATE TRIGGER rio_beneficiary_no_{operation.lower()}
                BEFORE {operation} ON beneficiary_claims BEGIN
                SELECT RAISE(ABORT, 'beneficiary claims are immutable'); END""")
    elif connection.dialect.name == 'postgresql':
        connection.exec_driver_sql("""CREATE FUNCTION rio_beneficiary_claim_immutable()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'beneficiary claims are immutable'; END; $$""")
        connection.exec_driver_sql("""CREATE TRIGGER rio_beneficiary_no_mutation
            BEFORE UPDATE OR DELETE ON beneficiary_claims FOR EACH ROW
            EXECUTE FUNCTION rio_beneficiary_claim_immutable()""")
    else:
        raise RuntimeError('Beneficiary claim immutability requires SQLite or PostgreSQL')


def drop_claim_guard_function(connection):
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('DROP FUNCTION IF EXISTS rio_beneficiary_claim_immutable()')
