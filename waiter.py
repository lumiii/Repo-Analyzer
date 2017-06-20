import time
import calendar
import ssl
import socket


def __wait_until(reset_time):
    wait_time = reset_time - calendar.timegm(time.gmtime())

    if wait_time > 0:
        print 'Waiting until: {}'.format(time.asctime(time.localtime(reset_time)))
        time.sleep(wait_time)


def wait_if_empty(github, calls_needed=1):
    remaining = github.rate_limiting[0]
    if remaining <= calls_needed:
        __wait_until(github.rate_limiting_resettime)


# repeatedly perform a network task that could fail until success
def retry(func, github):
    result = None
    while True:
        try:
            wait_if_empty(github, calls_needed=2)
            result = func()
        except (ssl.SSLError, socket.error) as e:
            continue

        break

    return result
