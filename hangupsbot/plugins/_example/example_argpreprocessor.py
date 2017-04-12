import plugins


def _initialise(bot):
    plugins.register_commands_argument_preprocessor_group(
        "exampleT",
        { r"^@@\w+" : test_resolver })

def test_resolver(token, external_context):
    return "!HELLOWORLD!"
