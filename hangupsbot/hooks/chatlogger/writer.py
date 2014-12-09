class logger():
    _bot = None

    def _on_chat_message(event):
        event.print_debug()

    def _on_membership_change(event):
        event.print_debug()

    def _on_rename(event):
        event.print_debug()
