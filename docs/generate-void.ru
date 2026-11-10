# SPARQL update computing VoID class and property partitions over all data graphs
# and storing them in the __VOID_GRAPH__ named graph (placeholder replaced by the `void` compose service)
PREFIX void: <http://rdfs.org/ns/void#>
PREFIX void-ext: <http://ldf.fi/void-ext#>

# Clear any previous VoID so it is not counted in the new statistics
DROP SILENT GRAPH <__VOID_GRAPH__> ;

INSERT {
  GRAPH <__VOID_GRAPH__> {
    ?dataset a void:Dataset ;
      void:classPartition ?cp .
    ?cp void:class ?stype ;
      void:propertyPartition ?pp .
    ?pp void:property ?p ;
      void:classPartition ?ocp ;
      void-ext:datatypePartition ?dtp .
    ?ocp void:class ?otype ;
      void:distinctSubjects ?scount ;
      void:distinctObjects ?ocount .
    ?dtp void-ext:datatype ?dt ;
      void:distinctSubjects ?scount ;
      void:distinctObjects ?ocount .
  }
}
WHERE {
  {
    # Objects that are typed resources
    SELECT ?stype ?p ?otype (COUNT(DISTINCT ?s) AS ?scount) (COUNT(DISTINCT ?o) AS ?ocount)
    WHERE {
      ?s ?p ?o .
      ?s a ?stype .
      ?o a ?otype .
    } GROUP BY ?stype ?p ?otype
  } UNION {
    # Objects that are literals, grouped on the datatype as a string
    # Language-tagged literals without datatype fall back to rdf:langString
    SELECT ?stype ?p ?dtStr (COUNT(DISTINCT ?s) AS ?scount) (COUNT(DISTINCT ?o) AS ?ocount)
    WHERE {
      ?s ?p ?o .
      ?s a ?stype .
      FILTER(isLiteral(?o))
      BIND(COALESCE(STR(DATATYPE(?o)), "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString") AS ?dtStr)
    } GROUP BY ?stype ?p ?dtStr
  }
  BIND(IRI(?dtStr) AS ?dt)
  # Stable IRIs so the same class/property partition is reused across rows
  BIND("__VOID_GRAPH__#" AS ?base)
  BIND(IRI(CONCAT(?base, "dataset")) AS ?dataset)
  BIND(IRI(CONCAT(?base, "cp_", MD5(STR(?stype)))) AS ?cp)
  BIND(IRI(CONCAT(?base, "pp_", MD5(CONCAT(STR(?stype), " ", STR(?p))))) AS ?pp)
  # Only one of these is bound per row, the other BIND errors and the related template triples are skipped
  BIND(IRI(CONCAT(?base, "ocp_", MD5(CONCAT(STR(?stype), " ", STR(?p), " ", STR(?otype))))) AS ?ocp)
  BIND(IRI(CONCAT(?base, "dtp_", MD5(CONCAT(STR(?stype), " ", STR(?p), " ", STR(?dt))))) AS ?dtp)
}
