"""
Middleware to replace the plain text message body of an error
response with one formatted so the client can parse it.

Based on pecan.middleware.errordocument
"""

from oslo_serialization import jsonutils


class ParsableErrorMiddleware(object):
    """Replace error body with something the client can parse."""
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Request for this state, modified by replace_start_response()
        # and used when an error is being reported.
        state = {}

        def replacement_start_response(status, headers, exc_info=None):
            """Overrides the default response to make errors parsable."""
            try:
                status_code = int(status.split(' ')[0])
                state['status_code'] = status_code
            except (ValueError, TypeError):  # pragma: nocover
                raise Exception(
                    'ParsableErrorMiddleware received an invalid '
                    'status %s' % status)

            if (state['status_code'] // 100) not in (2, 3):
                # Remove some headers so we can replace them later
                # when we have the full error message and can
                # compute the length.
                headers = [
                    (h, v) for (h, v) in headers
                    if h not in ('Content-Length', 'Content-Type')]

            # Save the headers in case we need to modify them.
            state['headers'] = headers
            return start_response(status, headers, exc_info)

        app_iter = self.app(environ, replacement_start_response)

        if (state['status_code'] // 100) not in (2, 3):
            app_iter = [i.decode('utf-8') for i in app_iter]
            body = [jsonutils.dumps({'error_message': '\n'.join(app_iter)})]
            body = [i.encode('utf-8') for i in body]
            state['headers'].append(('Content-Type', 'application/json'))
            state['headers'].append(('Content-Length', str(len(body[0]))))
        else:
            body = app_iter
        return body
