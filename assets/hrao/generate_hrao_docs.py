from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal
from jinja2 import Environment, FileSystemLoader


BASE = Path(__file__).resolve().parents[2]

PROJECT_ROOT = Path(__file__).resolve().parents[2] 
HRAO_DIR = PROJECT_ROOT / "assets" / "hrao"

TTL_IN = HRAO_DIR / "hrao_declaration.ttl"
RDF_OUT = HRAO_DIR / "hrao.rdf"
JSONLD_OUT = HRAO_DIR / "hrao.jsonld"
HTML_OUT = PROJECT_ROOT / "assets" / "html" / "hrao.html"

TEMPLATES_DIR = HRAO_DIR
TEMPLATE_NAME = "hrao.html.jinja"


DEFAULT_PREFIXES_BLOCK = """vd:      https://w3id.org/varela-digital/
hrao:    https://w3id.org/hrao/
fabio:   http://purl.org/spar/fabio/
frbr:    http://purl.org/vocab/frbr/core#
dcterms: http://purl.org/dc/terms/
foaf:    http://xmlns.com/foaf/0.1/
pro:     http://purl.org/spar/pro/
time:    http://www.w3.org/2006/time#
doco:    http://purl.org/spar/doco/
san:     http://purl.org/spar/san/
cnt:     http://www.w3.org/2011/content#
bio:     http://purl.org/vocab/bio/0.1/
owl:     http://www.w3.org/2002/07/owl#
rdf:     http://www.w3.org/1999/02/22-rdf-syntax-ns#
rdfs:    http://www.w3.org/2000/01/rdf-schema#
xml:     http://www.w3.org/XML/1998/namespace
xsd:     http://www.w3.org/2001/XMLSchema#
"""


@dataclass
class Creator:
    label: str
    uri: Optional[str] = None


@dataclass
class PropDoc:
    uri: str
    anchor: str
    label_short: str
    comment_short: str
    comment_full: str
    domain: Optional[str] = None
    range: Optional[str] = None
    inverse: Optional[str] = None
    is_symmetric: bool = False
    is_transitive: bool = False


def _to_str(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, Literal):
        return str(v)
    if isinstance(v, URIRef):
        return str(v)
    return str(v)


def _shorten(text: str, max_len: int = 140) -> str:
    t = " ".join(text.split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _anchor_from_uri(uri: str) -> str:
    # Use fragment or last path segment
    if "#" in uri:
        return uri.split("#", 1)[1]
    return uri.rstrip("/").rsplit("/", 1)[-1]


def main() -> None:
    if not TTL_IN.exists():
        raise FileNotFoundError(f"TTL not found at: {TTL_IN}")

    g = Graph()
    g.parse(TTL_IN, format="turtle")

    # Export alternative serializations
    g.serialize(destination=RDF_OUT, format="xml")
    g.serialize(destination=JSONLD_OUT, format="json-ld", indent=2)

    # Find ontology node (best effort)
    ontology_nodes = list(g.subjects(RDF.type, OWL.Ontology))
    ontology = ontology_nodes[0] if ontology_nodes else None

    ontology_uri = _to_str(ontology) or "https://w3id.org/hrao/"
    ontology_comment = _to_str(g.value(ontology, RDFS.comment)) if ontology else None

    # Creator extraction (best effort: dcterms:creator or dc:creator patterns sometimes appear)
    # If not present, keep empty.
    creators: List[Creator] = []

    # Collect object properties in the namespace
    props: List[PropDoc] = []
    for p in set(g.subjects(RDF.type, OWL.ObjectProperty)):
        uri = str(p)
        anchor = _anchor_from_uri(uri)

        label = _to_str(g.value(p, RDFS.label)) or anchor
        comment = _to_str(g.value(p, RDFS.comment)) or ""

        domain = _to_str(g.value(p, RDFS.domain))
        rng = _to_str(g.value(p, RDFS.range))
        inverse = _to_str(g.value(p, OWL.inverseOf))

        is_symmetric = (p, RDF.type, OWL.SymmetricProperty) in g
        is_transitive = (p, RDF.type, OWL.TransitiveProperty) in g

        props.append(
            PropDoc(
                uri=uri,
                anchor=anchor,
                label_short=label,
                comment_short=_shorten(comment, 160) if comment else "",
                comment_full=comment if comment else "",
                domain=domain,
                range=rng,
                inverse=inverse,
                is_symmetric=is_symmetric,
                is_transitive=is_transitive,
            )
        )

    props.sort(key=lambda x: x.label_short.lower())

    # Render HTML
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    template = env.get_template(TEMPLATE_NAME)

    html = template.render(
        title="HRAO — ontology | Varela Digital",
        heading="HRAO: Historical Relations from Annotated Objects",
        ontology_uri=ontology_uri,
        ontology_comment=ontology_comment,
        prefix="hrao",
        creators=creators,
        prefixes_block=DEFAULT_PREFIXES_BLOCK,
        properties=props,
    )

    HTML_OUT.write_text(html, encoding="utf-8")
    print("Generated:")
    print(f"- {HTML_OUT}")
    print(f"- {RDF_OUT}")
    print(f"- {JSONLD_OUT}")


if __name__ == "__main__":
    main()
    