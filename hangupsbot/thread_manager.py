from threading import Thread

threads = []

def start_thread(target, args):
    t = Thread(target=target, args=args)

    t.daemon = True
    t.start()

    threads.append(t)