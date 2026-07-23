class InvalidImageError(Exception):
    """Base class for anything wrong with an uploaded image."""


class ImageTooLargeError(InvalidImageError):
    pass


class ImageDimensionsTooLargeError(InvalidImageError):
    pass


class UnsupportedImageFormatError(InvalidImageError):
    pass
