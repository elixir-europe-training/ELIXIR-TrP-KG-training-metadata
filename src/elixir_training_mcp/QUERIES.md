# SPARQL Queries for Training Materials

This document contains SPARQL queries to search through the ELIXIR training materials RDF data.

## Find all Python courses

```sparql
PREFIX schema: <https://schema.org/>
PREFIX dct: <http://purl.org/dc/terms/>

SELECT ?course ?name ?description
WHERE {
  ?course a schema:Course ;
           schema:name ?name ;
           schema:description ?description .
  FILTER(CONTAINS(LCASE(?name), "python") || CONTAINS(LCASE(?description), "python"))
}
```

## Find courses by location and date range

```sparql
PREFIX schema: <https://schema.org/>

SELECT ?course ?name ?country ?locality ?startDate ?endDate
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:location ?location ;
            schema:startDate ?startDate ;
            schema:endDate ?endDate .
  ?location schema:address ?address .
  ?address schema:addressCountry ?country ;
           schema:addressLocality ?locality .
  FILTER(?startDate >= "2025-11-01"^^xsd:date && ?endDate <= "2025-12-31"^^xsd:date)
} ORDER BY ?startDate
```

## Find courses with specific learning outcomes

```sparql
PREFIX schema: <https://schema.org/>

SELECT ?course ?name ?teaches
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:teaches ?teaches .
  FILTER(CONTAINS(LCASE(?teaches), "ansible") || CONTAINS(LCASE(?teaches), "galaxy"))
}
```

## Find all courses provided by a specific organization

```sparql
PREFIX schema: <https://schema.org/>

SELECT ?course ?name ?provider
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:provider ?providerOrg .
  ?providerOrg schema:name ?provider .
  FILTER(?provider = "GTN" || ?provider = "Bioinformatics.ca")
}
```

## Find courses with prerequisites

```sparql
PREFIX schema: <https://schema.org/>

SELECT ?course ?name ?prerequisites
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:coursePrerequisites ?prerequisites .
}
```

## Find courses by capacity and course mode

```sparql
PREFIX schema: <https://schema.org/>

SELECT ?course ?name ?mode ?capacity ?country
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:courseMode ?mode ;
            schema:maximumAttendeeCapacity ?capacity ;
            schema:location ?location .
  ?location schema:address ?address .
  ?address schema:addressCountry ?country .
  FILTER(?capacity > 20)
} ORDER BY DESC(?capacity)
```

## Find courses with multiple funding organizations

```sparql
PREFIX schema: <https://schema.org/>

SELECT ?course ?name (COUNT(?funder) as ?funderCount) ?funderNames
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:funder ?funderOrg .
  ?funderOrg schema:name ?funderNames .
} GROUP BY ?course ?name HAVING(COUNT(?funder) > 1)
```

## Find courses organized by a specific person

```sparql
PREFIX schema: <https://schema.org/>

SELECT ?course ?name ?organizer
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:organizer ?organizerOrg .
  ?organizerOrg schema:name ?organizer .
  FILTER(CONTAINS(?organizer, "Martin Čech"))
}
```

## Find courses with specific keywords or topics

```sparql
PREFIX schema: <https://schema.org/>
PREFIX edam: <http://edamontology.org/>

SELECT ?course ?name ?keywords ?topics
WHERE {
  ?course a schema:Course ;
          schema:name ?name .
  OPTIONAL { ?course schema:keywords ?keywords . }
  OPTIONAL { ?course schema:about ?topics . }
  FILTER(CONTAINS(LCASE(?keywords), "admin") || CONTAINS(LCASE(?keywords), "galaxy"))
}
```

## Find upcoming courses near a geographic location

```sparql
PREFIX schema: <https://schema.org/>

SELECT ?course ?name ?locality ?distance ?startDate
WHERE {
  ?course a schema:Course ;
          schema:name ?name ;
          schema:hasCourseInstance ?instance .
  ?instance schema:location ?location ;
            schema:startDate ?startDate .
  ?location schema:latitude ?lat ;
            schema:longitude ?lon ;
            schema:address ?address .
  ?address schema:addressLocality ?locality .
  # Filter for courses in Canada as example
  FILTER(CONTAINS(?locality, "Toronto") || CONTAINS(?locality, "Halifax") || CONTAINS(?locality, "Vancouver"))
} ORDER BY ?startDate
```

## Find courses and learning resources made by authors/contributors/instructors who also made materials for social sciences
```sparql
PREFIX schema: <https://schema.org/>

SELECT DISTINCT ?person ?personName ?itemType ?item ?title ?role ?instance ?start WHERE {
  # people behind a social-science item
  VALUES ?seedCls { schema:Course schema:LearningResource }
  ?seed a ?seedCls .
  VALUES ?seedProp { schema:name schema:keywords schema:description }
  ?seed ?seedProp ?seedText .
  FILTER(REGEX(LCASE(STR(?seedText)), "social[ -]?sci"))

  {
    ?seed schema:hasCourseInstance ?seedInstance .
    ?seedInstance schema:instructor ?person .
  }
  UNION
  {
    VALUES ?seedRel { schema:author schema:contributor }
    ?seed ?seedRel ?person .
  }

  FILTER(isIRI(?person))
  ?person a schema:Person .
  OPTIONAL { ?person schema:name ?personName }

  # everything that person made or taught
  VALUES ?itemCls { schema:Course schema:LearningResource }
  ?item a ?itemCls .
  BIND(STRAFTER(STR(?itemCls), "https://schema.org/") AS ?itemType)
  OPTIONAL { ?item schema:name ?title }

  {
    ?item schema:hasCourseInstance ?instance .
    ?instance schema:instructor ?person .
    OPTIONAL { ?instance schema:startDate ?start }
    BIND("instructor" AS ?role)
  }
  UNION
  {
    VALUES ?rel { schema:author schema:contributor }
    ?item ?rel ?person .
    BIND(STRAFTER(STR(?rel), "https://schema.org/") AS ?role)
  }
}
ORDER BY ?personName ?itemType ?item
```


## Find all Bioconductor courses and learning resources on a particular topic, e.g. single-cell sequencing

```sparql
PREFIX schema: <https://schema.org/>

SELECT DISTINCT ?type ?item ?title ?evidence ?detail WHERE {
  VALUES ?cls { schema:Course schema:LearningResource }
  ?item a ?cls .
  BIND(STRAFTER(STR(?cls), "https://schema.org/") AS ?type)
  OPTIONAL { ?item schema:name ?title }

  # linked, named entity -- mentions / author / provider / organizer
  {
    VALUES (?prop ?evidence) {
      (schema:mentions   "mentions")
      (schema:author     "author")
      (schema:provider   "provider")
      (schema:organizer  "organizer")
    }
    ?item ?prop ?node .
    ?node schema:name ?nodeName .
    FILTER(REGEX(LCASE(STR(?nodeName)), "bioconductor"))
    BIND(CONCAT(STR(?nodeName), " <", STR(?node), ">") AS ?detail)
  }
  UNION
  # free text on the item
  {
    VALUES (?prop ?evidence) {
      (schema:name        "name")
      (schema:description "description")
      # (schema:keywords    "keywords")
    }
    ?item ?prop ?text .
    FILTER(REGEX(LCASE(STR(?text)), "bioconductor") &&
         REGEX(LCASE(STR(?text)), "single[ -]?cell"))
    BIND(SUBSTR(STR(?text), 1, 120) AS ?detail)
  }
}
ORDER BY ?type ?item ?evidence
```


