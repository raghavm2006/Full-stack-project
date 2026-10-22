from flask import Request


class MailUploadRequest(Request):
    @property
    def max_content_length(self):
        if self.path == "/mail/prepare":
            return 15 * 1024 * 1024
        return super().max_content_length
