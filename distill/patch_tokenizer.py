#!/usr/bin/env python3
"""Normalize tokenizer_config.json so llama.cpp's converter can load it.

transformers 5.x writes tokenizer_class=TokenizersBackend, which the pinned
llama.cpp converter does not know. Rewrite to the generic fast tokenizer class.
"""
import json
import sys

p = sys.argv[1] if len(sys.argv) > 1 else "out/merged/tokenizer_config.json"
d = json.load(open(p))
d["tokenizer_class"] = "PreTrainedTokenizerFast"
d.pop("auto_map", None)
json.dump(d, open(p, "w"), indent=1)
print("patched", p, "->", d["tokenizer_class"])
