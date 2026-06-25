# Environment Setup

This project uses a separate Conda/Mamba environment so the shared Miniforge
`base` environment is not modified.

## What is already installed

- Miniforge: `/home/mspirzewski/miniforge3`
- Conda: `26.3.2`
- Mamba: `2.5.0`
- Base Python: `3.13.12`
- System `latexmk`: `4.76`

Not currently available globally:

- `pandoc`
- `streamlit`
- `pymupdf`
- `pdfplumber`
- `tesseract`

## Create the app environment

From the project directory:

```bash
cd /home/mspirzewski/git/sapphire/document_transformation
source ~/miniforge3/bin/activate
mamba env create -f environment.yml
```

Activate it:

```bash
conda activate document-transformation
```

Check the important tools:

```bash
python --version
streamlit --version
pandoc --version
latexmk --version
```

`latexmk` is already installed system-wide, so it does not need to be installed
inside this environment for the first MVP.

## Run the app

```bash
cd /home/mspirzewski/git/sapphire/document_transformation
source ~/miniforge3/bin/activate
conda activate document-transformation
streamlit run app.py
```

Streamlit will print a local URL, usually `http://localhost:8501`.

## Compile a generated LaTeX project

From inside one generated project folder:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

The converter generates standalone LaTeX and patches common Word symbols so
`pdflatex` can compile them on this machine.

## PDF conversion notes

PDF conversion is currently a draft generator for digital PDFs:

- PyMuPDF extracts page text.
- pdfplumber extracts detected tables.
- The app writes `main.tex`, `tables/`, and `notes/conversion_warnings.md`.

Scanned/image-only PDFs, equations, figures, captions, and complex page layouts
will still need manual review.

After conversion, the Streamlit app shows a review workbench:

- left: editable generated LaTeX source
- middle: PDF compiled from the generated LaTeX
- right: original uploaded PDF

Use `Compile generated PDF` after editing the LaTeX source to refresh the middle
preview.

## Later updates

To add packages later without changing `base`, edit `environment.yml` and run:

```bash
source ~/miniforge3/bin/activate
conda activate document-transformation
mamba env update -f environment.yml --prune
```

Avoid running package installs while `base` is active.
