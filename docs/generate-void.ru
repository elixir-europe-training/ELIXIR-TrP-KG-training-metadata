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
      void:entities ?entities ;
      void:propertyPartition ?pp .
    ?pp void:property ?p ;
      void:triples ?ptriples ;
      void:classPartition ?ocp ;
      void-ext:datatypePartition ?dtp .
    ?ocp void:class ?otype ;
      void:triples ?otriples .
    ?dtp void-ext:datatype ?dt ;
      void:triples ?dtriples .
  }
}
WHERE {
  # Each branch binds a different subset of variables, template triples with unbound variables are skipped
  {
    # Number of instances of each class
    SELECT ?stype (COUNT(?s) AS ?entities)
    WHERE {
      ?s a ?stype .
    } GROUP BY ?stype
  } UNION {
    # Number of triples for each property used by instances of a class
    SELECT ?stype ?p (COUNT(*) AS ?ptriples)
    WHERE {
      ?s a ?stype ;
        ?p ?o .
    } GROUP BY ?stype ?p
  } UNION {
    # Objects that are typed resources
    SELECT ?stype ?p ?otype (COUNT(*) AS ?otriples)
    WHERE {
      ?s ?p ?o .
      ?s a ?stype .
      ?o a ?otype .
    } GROUP BY ?stype ?p ?otype
  } UNION {
    # Objects that are literals, grouped on the datatype as a string
    # Language-tagged literals without datatype fall back to rdf:langString
    SELECT ?stype ?p ?dtStr (COUNT(*) AS ?dtriples)
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
  BIND(IRI(CONCAT(?base, "ocp_", MD5(CONCAT(STR(?stype), " ", STR(?p), " ", STR(?otype))))) AS ?ocp)
  BIND(IRI(CONCAT(?base, "dtp_", MD5(CONCAT(STR(?stype), " ", STR(?p), " ", STR(?dt))))) AS ?dtp)
}
