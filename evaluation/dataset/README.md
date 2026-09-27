# Recognition Evaluation Dataset

Add evaluation images using this layout:

```text
dataset/
├── known/
│   └── Student Name/
│       ├── normal.jpg
│       ├── lighting/bright.jpg
│       ├── angle/left.jpg
│       └── distance/far.jpg
└── unknown/
    └── unknown-person.jpg
```

Known images are labeled from the student directory name. Unknown images must
not match anyone in the application `Known/` gallery. The optional
`manifest.json` file can provide explicit `path`, `expected`, and `condition`
values when directory names are not enough.

Run the evaluator from the project root:

```text
python evaluation/evaluate_recognition.py
```

Use `--gallery` to evaluate against a different gallery, or `--output` to
write the report somewhere else. Condition values such as `lighting`, `angle`,
and `distance` are reported separately in `results.json`.