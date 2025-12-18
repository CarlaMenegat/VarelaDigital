from lxml import etree
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, XSD, DCTERMS
from rdflib.namespace import PROV

# =========================
# Namespaces
# =========================

BASE = Namespace("https://vareladigital.github.io/resource/")

FABIO = Namespace("http://purl.org/spar/fabio/")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
PRO = Namespace("http://purl.org/spar/pro/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
DOCO = Namespace("http://purl.org/spar/doco/")
C4O = Namespace("http://purl.org/spar/c4o/")
SAN = Namespace("http://www.ontologydesignpatterns.org/cp/owl/semanticannotation.owl#")
FRBR = Namespace("http://purl.org/vocab/frbr/core#")
PROV_NS = Namespace("http://www.w3.org/ns/prov#")

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

# =========================
# Parse TEI
# =========================

def parse_tei(path):
    tree = etree.parse(path)
    root = tree.getroot()
    return root

# =========================
# Document (C1)
# =========================

def build_document(graph, doc_id):
    doc_uri = BASE[doc_id]
    graph.add((doc_uri, RDF.type, FABIO.Letter))
    return doc_uri

# =========================
# Correspondence (C1)
# =========================

def extract_correspondence(root, graph, doc_uri):
    sent_actions = root.xpath("//tei:correspAction[@type='sent']", namespaces=TEI_NS)
    received_actions = root.xpath("//tei:correspAction[@type='received']", namespaces=TEI_NS)

    for action in sent_actions:
        for p in action.xpath(".//tei:persName[@ref]", namespaces=TEI_NS):
            graph.add((doc_uri, DCTERMS.creator, BASE[p.get("ref").lstrip("#")]))

        for place in action.xpath(".//tei:placeName[@ref]", namespaces=TEI_NS):
            graph.add((doc_uri, DCTERMS.spatial, BASE[place.get("ref").lstrip("#")]))

        date = action.xpath(".//tei:date/@when", namespaces=TEI_NS)
        if date:
            graph.add((doc_uri, DCTERMS.date, Literal(date[0], datatype=XSD.date)))

    for action in received_actions:
        for p in action.xpath(".//tei:persName[@ref]", namespaces=TEI_NS):
            graph.add((doc_uri, PRO.addressee, BASE[p.get("ref").lstrip("#")]))

# =========================
# Global Mentions (C1)
# =========================

def extract_mentions(root, graph, doc_uri):
    refs = root.xpath("//tei:persName[@ref] | //tei:placeName[@ref] | //tei:orgName[@ref]",
                      namespaces=TEI_NS)
    for r in refs:
        graph.add((doc_uri, DCTERMS.references, BASE[r.get("ref").lstrip("#")]))

# =========================
# TextChunks (C2)
# =========================

def extract_text_chunks(root, graph, doc_uri):

    TEXTCHUNK_RULES = {
        "paragraph": {
            "xpath": "//tei:div[@type='letter']//tei:p",
            "tei_type": "paragraph"
        },
        "postscript": {
            "xpath": "//tei:postscript",
            "tei_type": "postscript"
        },
        "endorsement": {
            "xpath": "//tei:note[@type='endorsement']",
            "tei_type": "endorsement"
        },
        "heading": {
            "xpath": "//tei:head",
            "tei_type": "heading"
        }
    }

    chunk_counter = 1

    for rule in TEXTCHUNK_RULES.values():
        nodes = root.xpath(rule["xpath"], namespaces=TEI_NS)

        for node in nodes:
            chunk_uri = URIRef(f"{doc_uri}_chunk_{chunk_counter}")

            graph.add((doc_uri, FRBR.part, chunk_uri))
            graph.add((chunk_uri, RDF.type, DOCO.TextChunk))
            graph.add((chunk_uri, DCTERMS.type, Literal(rule["tei_type"])))

            text = "".join(node.itertext()).strip()
            if text:
                graph.add((chunk_uri, C4O.hasContent, Literal(text)))

            # Entity references inside the chunk
            for ref in node.xpath(
                ".//tei:persName[@ref] | .//tei:placeName[@ref] | .//tei:orgName[@ref]",
                namespaces=TEI_NS
            ):
                graph.add((chunk_uri, SAN.refersTo, BASE[ref.get("ref").lstrip("#")]))

            # Hand attribution (material authorship)
            hand = node.get("hand")
            if hand:
                graph.add((
                    chunk_uri,
                    PROV_NS.wasAttributedTo,
                    BASE[hand.lstrip("#")]
                ))

            chunk_counter += 1

# =========================
# Main pipeline
# =========================

def tei_to_rdf(tei_path, output_path, doc_id):
    graph = Graph()

    # Bind prefixes
    graph.bind("base", BASE)
    graph.bind("fabio", FABIO)
    graph.bind("foaf", FOAF)
    graph.bind("pro", PRO)
    graph.bind("geo", GEO)
    graph.bind("dcterms", DCTERMS)
    graph.bind("doco", DOCO)
    graph.bind("c4o", C4O)
    graph.bind("san", SAN)
    graph.bind("frbr", FRBR)
    graph.bind("prov", PROV_NS)

    root = parse_tei(tei_path)

    doc_uri = build_document(graph, doc_id)
    extract_correspondence(root, graph, doc_uri)
    extract_mentions(root, graph, doc_uri)
    extract_text_chunks(root, graph, doc_uri)

    graph.serialize(destination=output_path, format="turtle")

# =========================
# CLI usage example
# =========================

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        print("Usage: python tei_to_rdf.py <tei.xml> <output.ttl> <doc_id>")
        sys.exit(1)

    tei_path = sys.argv[1]
    output_path = sys.argv[2]
    doc_id = sys.argv[3]

    tei_to_rdf(tei_path, output_path, doc_id)