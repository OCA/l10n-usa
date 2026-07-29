# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

# Mini SST rate file: WY (FIPS 56) state 4% (reduced food/drug 2%),
# Laramie county (021) 1%, one special district (55555) 0.5%.
# 9 positional columns, no header: state,jtype,fips,gen_intra,gen_inter,
# food_intra,food_inter,begin,end.
RATE_CSV = "\n".join(
    [
        "56,45,56,0.04,0.04,0.02,0.02,20200101,29991231",
        "56,00,021,0.01,0.01,0,0,20200101,29991231",
        "56,63,55555,0.005,0.005,0,0,20200101,29991231",
    ]
)


def boundary_row(
    zip5="82001",
    fips_state="56",
    fips_county="021",
    districts=("55555",),
    record_type="Z",
):
    """Build one boundary row (≥29 fixed cols + N district triplets)."""
    row = [""] * 29
    row[0] = record_type
    row[1] = "20200101"
    row[2] = "29991231"
    row[14] = "CHEYENNE"
    row[15] = zip5
    row[17] = zip5  # zip_low
    row[19] = zip5  # zip_high
    row[22] = fips_state
    row[23] = fips_state  # state indicator = state FIPS → state tax applies
    row[24] = fips_county
    row[25] = "00000"  # no place
    for district in districts:
        row += ["ST", district, "63"]  # special-district triplet(s)
    return ",".join(row)


BOUNDARY_CSV = boundary_row()
