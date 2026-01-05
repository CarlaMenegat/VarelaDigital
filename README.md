# Varela Digital

Varela Digital is a digital scholarly editing project focused on the *Coleção Varela*, published in volume II of the *Anais do Arquivo Histórico do Rio Grande do Sul*. The project aims to provide a structured, interoperable, and methodologically transparent digital edition of nineteenth-century documents, primarily correspondence related to the Farroupilha Revolution.

The edition is based on TEI P5 encoding and adopts a layered editorial architecture that clearly separates textual encoding, structural transformation, presentation, and semantic representation. Within this framework, TEI documents function as a pivot representation: they constitute the sole authoritative source of textual evidence, editorial responsibility, and provenance, from which all other representations are derived in a controlled and reproducible manner.

At its current stage, the project includes a pilot corpus of approximately 250 documents and serves as the basis for a Master’s thesis in Digital Humanities and Digital Knowledge (University of Bologna).

---

## TEI Encoding and Derived Representations

All documents in Varela Digital are encoded in TEI P5, following consistent editorial and structural principles. No interpretation, inference, or enrichment is introduced outside the TEI and its associated standoff annotation layers.

From this authoritative source, multiple derived representations can be generated, including static HTML and semantic serialisations (RDF and JSON-LD). These outputs are conceived as projections of the TEI source, not as alternative editions.

---

## XSLT Transformation and Static HTML

The project includes an XSLT stylesheet designed to transform TEI P5 documents into static HTML representations. This transformation is intentionally minimal and non-interpretative. Its purpose is to provide a readable and structurally faithful HTML rendering of each document, serving both as a reading interface and as a validation layer for the TEI encoding.

The XSLT preserves the internal structure of the documents—such as headings, paragraphs, lists, page breaks, and figures—while exposing existing document types and attributes. No semantic interpretation, annotation, or interactive behaviour is introduced at this stage.

The resulting HTML files are standalone and can be accessed directly. Any interactive features (such as annotation display or entity navigation) are conceived as a separate JavaScript layer applied on top of the static structure.

---

## Batch Processing with Saxon

XSLT stylesheets cannot be executed on their own and require an external processor. Since the stylesheet used in Varela Digital relies on XSLT 2.0 features, a processor supporting this version of the specification is required.

The project uses **Saxon-HE (Home Edition)**, a widely adopted open-source XSLT processor running on the Java Virtual Machine and supporting XSLT 2.0 and 3.0. The Saxon-HE JAR file is not included in the repository and must be downloaded separately and placed locally in the directory: tools/saxon/saxon-he.jar 

This file is intentionally excluded from version control, as it is an external dependency and not part of the scholarly content of the project.

To generate static HTML files for the entire corpus, the project provides a batch transformation script. This script applies the same XSLT stylesheet to all TEI files located in: data/documents_XML/ and produces one HTML file per document in: data/documents_HTML/ 

This batch process ensures transparency, reproducibility, and a clear separation between authoritative sources and derived outputs.

---

## Licensing

All original content produced within the Varela Digital project is released under the **Creative Commons Attribution 4.0 International License (CC BY 4.0)**, unless otherwise stated.