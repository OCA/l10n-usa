# Copyright 2019 Eficent Business and IT Consulting Services S.L.
# - (https://www.eficent.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).


def scrub_string(string, replacement):
    b_string = string.encode('utf-8')
    b_replacement = replacement.encode('utf-8')

    def before_record_response(response):
        response['body']['string'] = response['body'][
            'string'].replace(b_string, b_replacement)
        return response

    return before_record_response
