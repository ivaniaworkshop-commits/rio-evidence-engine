"""Database guards for recorded reviews; database owners can still alter them."""


def install_review_guards(connection):
    if connection.dialect.name == 'sqlite':
        connection.exec_driver_sql("""CREATE TRIGGER rio_review_no_update
            BEFORE UPDATE ON reconciliation_reviews BEGIN
            SELECT RAISE(ABORT, 'reconciliation reviews are immutable'); END""")
        connection.exec_driver_sql("""CREATE TRIGGER rio_review_no_delete
            BEFORE DELETE ON reconciliation_reviews BEGIN
            SELECT RAISE(ABORT, 'reconciliation reviews are immutable'); END""")
    elif connection.dialect.name == 'postgresql':
        connection.exec_driver_sql("""CREATE FUNCTION rio_reconciliation_review_immutable()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'reconciliation reviews are immutable'; END; $$""")
        connection.exec_driver_sql("""CREATE TRIGGER rio_review_no_mutation
            BEFORE UPDATE OR DELETE ON reconciliation_reviews FOR EACH ROW
            EXECUTE FUNCTION rio_reconciliation_review_immutable()""")
    else:
        raise RuntimeError('Review immutability requires SQLite or PostgreSQL')


def drop_review_guard_function(connection):
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('DROP FUNCTION IF EXISTS rio_reconciliation_review_immutable()')
