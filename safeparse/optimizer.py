# optimizer.py — Groups fields for bounds-check merging.
#
# In "naive" mode, every field gets its own bounds check.
# In "optimized" mode, consecutive fixed-size fields are merged
# into a single group with one combined bounds check.
#
# This reduces the number of comparisons in the generated C code
# without changing the safety guarantees.  The key insight is:
# if we know we need N bytes for the next M fields, we can check
# once instead of M times.

from safeparse.parser import IntegerType, BytesType


# Map from type name to byte size.
TYPE_SIZES = {
    "u8":    1,
    "u16":   2,
    "u32":   4,
    "u16le": 2,
    "u32le": 4,
}


class FieldGroup:
    """
    A group of fields that share one bounds check.

    WHAT: Holds one or more fields and the total number of bytes
          they consume.
    WHY:  The code generator emits one bounds check per FieldGroup,
          so merging consecutive fixed-size fields into one group
          reduces the number of checks.
    """

    def __init__(self, fields, total_size, is_fixed):
        self.fields = fields            # list of Field objects
        self.total_size = total_size    # total bytes (0 for variable)
        self.is_fixed = is_fixed        # True if all fields are fixed-size


def make_field_groups(field_list, mode):
    """
    Split fields into groups based on the optimization mode.

    WHAT: Returns a list of FieldGroup objects.
    WHY:  The code generator uses these groups to decide how many
          bounds checks to emit and where to place them.

    mode is "naive" or "optimized".
    """
    if mode == "naive":
        return _naive_groups(field_list)
    if mode == "optimized":
        return _optimized_groups(field_list)
    raise ValueError(
        "Unknown mode: {!r} (must be 'naive' or 'optimized')".format(mode)
    )


def _naive_groups(field_list):
    """
    Create one group per field (no merging at all).

    WHAT: Wraps every field in its own FieldGroup.
    WHY:  This is the simplest and most obviously correct strategy.
          Each field gets its own bounds check, making it easy to
          verify safety but potentially slower.
    """
    groups = []

    for field in field_list:
        if isinstance(field.field_type, IntegerType):
            size = TYPE_SIZES[field.field_type.type_name]
            group = FieldGroup([field], size, True)
            groups.append(group)
        elif isinstance(field.field_type, BytesType):
            group = FieldGroup([field], 0, False)
            groups.append(group)

    return groups


def _optimized_groups(field_list):
    """
    Merge consecutive fixed-size fields into larger groups.

    WHAT: Scans through the field list.  While fields are fixed-size,
          accumulates them into one group.  When a variable-size
          bytes[] field appears, the accumulated group is flushed
          and the bytes[] field gets its own (non-mergeable) group.

    WHY:  If we have four u16 fields in a row (8 bytes total), we
          only need ONE check "are there at least 8 bytes left?"
          instead of four separate checks.
    """
    groups = []

    # Accumulator for consecutive fixed-size fields.
    current_fixed_fields = []
    current_fixed_size = 0

    for field in field_list:
        if isinstance(field.field_type, IntegerType):
            # This field is fixed-size — accumulate it.
            size = TYPE_SIZES[field.field_type.type_name]
            current_fixed_fields.append(field)
            current_fixed_size = current_fixed_size + size

        elif isinstance(field.field_type, BytesType):
            # Flush any accumulated fixed-size fields first.
            if current_fixed_fields:
                group = FieldGroup(
                    list(current_fixed_fields),
                    current_fixed_size,
                    True,
                )
                groups.append(group)
                current_fixed_fields = []
                current_fixed_size = 0

            # The bytes[] field always gets its own group because its
            # size depends on a value we only know at runtime.
            group = FieldGroup([field], 0, False)
            groups.append(group)

    # Don't forget any remaining fixed-size fields after the loop.
    if current_fixed_fields:
        group = FieldGroup(
            list(current_fixed_fields),
            current_fixed_size,
            True,
        )
        groups.append(group)

    return groups
