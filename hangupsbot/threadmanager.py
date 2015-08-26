from threading import Thread

from plugins import tracking


threads = []


def start_thread(target, args):
    t = Thread(target=target, args=args)

    t.daemon = True
    t.start()

    threads.append(t)

    tracking.register_thread(t)
