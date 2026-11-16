"""Ordinary-write guards for provider observations; DB administrators remain trusted."""


def install_provider_observation_guards(connection):
    if connection.dialect.name == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            connection.exec_driver_sql(f"""CREATE TRIGGER rio_provider_observation_no_{operation.lower()}
                BEFORE {operation} ON provider_account_observations BEGIN
                SELECT RAISE(ABORT, 'provider observations are immutable'); END""")
    elif connection.dialect.name == 'postgresql':
        connection.exec_driver_sql("""CREATE FUNCTION rio_provider_observation_immutable()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'provider observations are immutable'; END; $$""")
        connection.exec_driver_sql("""CREATE TRIGGER rio_provider_observation_no_mutation
            BEFORE UPDATE OR DELETE ON provider_account_observations FOR EACH ROW
            EXECUTE FUNCTION rio_provider_observation_immutable()""")
    else:
        raise RuntimeError('Provider observations require SQLite or PostgreSQL')


def drop_provider_observation_guard_function(connection):
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('DROP FUNCTION IF EXISTS rio_provider_observation_immutable()')
