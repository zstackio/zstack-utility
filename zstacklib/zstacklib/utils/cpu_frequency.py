import re


_GHZ_IN_MODEL_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*GHz", re.IGNORECASE)
_DMI_MHZ_PATTERN = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*MHz\s*$", re.IGNORECASE | re.MULTILINE)


def get_static_cpu_ghz(model_name, processor_frequencies):
    model_match = _GHZ_IN_MODEL_PATTERN.search(model_name or "")
    if model_match and float(model_match.group(1)) > 0:
        return model_match.group(1)

    frequency_lines = [
        line.strip()
        for line in (processor_frequencies or "").splitlines()
        if line.strip()
    ]
    frequencies = []
    for line in frequency_lines:
        frequency_match = _DMI_MHZ_PATTERN.match(line)
        if not frequency_match:
            return None
        frequencies.append(float(frequency_match.group(1)))

    if not frequencies or min(frequencies) <= 0:
        return None

    if max(frequencies) - min(frequencies) > 1:
        return None

    return "%.2f" % (sum(frequencies) / len(frequencies) / 1000)
