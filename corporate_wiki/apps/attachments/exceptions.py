class InvalidAttachmentError(Exception):
    """Base class for anything wrong with an uploaded attachment."""


class AttachmentTooLargeError(InvalidAttachmentError):
    pass


class UnsupportedAttachmentFormatError(InvalidAttachmentError):
    pass
