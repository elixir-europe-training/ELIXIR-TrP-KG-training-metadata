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


## Find learning resources that are based on Python 3
```sparql
PREFIX schema: <https://schema.org/>

SELECT DISTINCT ?s ?name ?dp ?dm
WHERE {
  ?s a ?c .
  FILTER((?c IN (schema:LearningResource, <https://schema.org/LearningResource>)) || (?c IN (schema:Course, <https://schema.org/Course>)))
  ?s schema:name ?name .

  # strict Python-3 match: avoids "python", "python 2", "python 3D"
  ?s ?p ?v .
  FILTER(REGEX(LCASE(STR(?v)), "python ?3(\\.\\d+)?"))

  OPTIONAL { ?s schema:datePublished ?dp }
  OPTIONAL { ?s schema:dateModified  ?dm }
}
ORDER BY DESC(?dp) DESC(?dm)
LIMIT 25
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

## Find all learning resources that use a certain package, e.g. scanpy
```
PREFIX schema: <https://schema.org/>

SELECT ?mat ?name (MAX(?dp) AS ?pub)
WHERE {
  ?mat a schema:LearningResource ;
       schema:name ?name .

  OPTIONAL { ?mat schema:datePublished ?dp }

  FILTER EXISTS {
    { ?mat schema:mentions ?m . ?m schema:name ?tool }   # structured: bio.tools record
    UNION { ?mat schema:description ?tool }
    UNION { ?mat schema:keywords    ?tool }
    UNION { ?mat schema:name        ?tool }
    FILTER(CONTAINS(LCASE(STR(?tool)), "scanpy"))
  }
}
GROUP BY ?mat ?name
ORDER BY DESC(?pub)
```

## Find all course (event) organisers in a specific country and the number of courses they organised
```sparql
PREFIX schema: <https://schema.org/>

SELECT ?key
       (SAMPLE(?orgName) AS ?organizer)
       (SAMPLE(?url) AS ?orgUrl)
       (COUNT(DISTINCT ?event) AS ?events)
WHERE {
  ?event a schema:Event ;
         schema:organizer ?org ;
         schema:location ?loc .
  ?loc schema:address ?addr .
  ?addr schema:addressCountry ?country .
  ?org schema:name ?orgName .
  OPTIONAL { ?org schema:url ?url }
  BIND(COALESCE(?url, STR(?orgName)) AS ?key)
  FILTER(?country = "Switzerland")
}
GROUP BY ?key
ORDER BY DESC(?events)
```

## Get the number of instructors per country, in which a course has taken place
```sparql
PREFIX schema: <https://schema.org/>

SELECT ?country
       (COUNT(DISTINCT ?c) AS ?courses)
       (COUNT(DISTINCT ?p) AS ?instructors)
WHERE {
  ?c a schema:Course ;
     schema:hasCourseInstance ?ci .
  ?ci schema:instructor ?p ;
      schema:location ?loc .
  ?loc schema:address ?a .
  ?a schema:addressCountry ?country .
  FILTER(isIRI(?p))
}
GROUP BY ?country
ORDER BY DESC(?instructors)
```

## Find all instructors in a particular country
```sparql
PREFIX schema: <https://schema.org/>

SELECT DISTINCT ?country ?instructor ?instructorName ?course ?courseName ?instance ?start WHERE {
  VALUES ?country { "United Kingdom" }          # <-- exact string, single knob

  ?course a schema:Course ;
          schema:hasCourseInstance ?instance .
  ?instance schema:instructor ?instructor ;
            schema:location ?loc .
  ?loc schema:address ?addr .
  ?addr schema:addressCountry ?country .

  FILTER(isIRI(?instructor))

  OPTIONAL { ?instructor schema:name ?instructorName }
  OPTIONAL { ?course     schema:name ?courseName }
  OPTIONAL { ?instance   schema:startDate ?start }
}
ORDER BY ?instructorName ?start
```

## Get the number of courses a provider organized in a particular year, e.g. 2024

```sparql
PREFIX schema: <https://schema.org/>

SELECT ?providerUrl ?providerName
       (COUNT(DISTINCT ?provider) AS ?nodes)
       (COUNT(DISTINCT ?course)   AS ?courses)
WHERE {
  VALUES ?year { "2024" }                    # <-- year to look for

  ?course a schema:Course ;
          schema:provider ?provider ;
          schema:hasCourseInstance ?instance .

  ?instance schema:startDate ?start .
  FILTER(STRSTARTS(STR(?start), ?year))

  ?provider schema:url  ?providerUrl ;
            schema:name ?providerName .
}
GROUP BY ?providerUrl ?providerName
ORDER BY DESC(?courses)
```