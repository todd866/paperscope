"""Regression test for the PubMed DOI-parse bug.

A recursive `.//ArticleIdList/ArticleId` search also matches every cited
reference's ArticleIdList (under PubmedData/ReferenceList/Reference), and the
loop kept the *last* match — so for any record carrying reference DOIs the
article's own DOI was clobbered by a reference's DOI. That silently mis-DOI-ed
~1 in 4 MEDLINE records (real-but-wrong DOIs, correct titles). The parser must
return the article's OWN doi (ELocationID, or the article's own ArticleIdList),
never a reference's.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from paperscope.systematic_review.search.medline import _parse_article

# Article doi in PubmedData/ArticleIdList differs from cited-reference doi(s).
ARTICLE_WITH_REFERENCE_DOIS = """
<PubmedArticle>
  <MedlineCitation>
    <PMID>15106121</PMID>
    <Article>
      <Journal><Title>Am J Hum Genet</Title>
        <JournalIssue><PubDate><Year>2004</Year></PubDate></JournalIssue></Journal>
      <ArticleTitle>Antecedent soil-moisture thresholds in a form of urban flash flooding</ArticleTitle>
      <AuthorList><Author><LastName>Chen</LastName><Initials>YZ</Initials></Author></AuthorList>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList>
      <ArticleId IdType="pubmed">15106121</ArticleId>
      <ArticleId IdType="doi">10.1086/421054</ArticleId>
    </ArticleIdList>
    <ReferenceList>
      <Reference><Citation>Ref A</Citation><ArticleIdList>
        <ArticleId IdType="doi">10.1038/ng1001-160</ArticleId></ArticleIdList></Reference>
      <Reference><Citation>Ref B</Citation><ArticleIdList>
        <ArticleId IdType="doi">10.9999/another-reference</ArticleId></ArticleIdList></Reference>
    </ReferenceList>
  </PubmedData>
</PubmedArticle>
"""

# DOI present only as an ELocationID under Article; a reference also has a doi.
ARTICLE_WITH_ELOCATION_DOI = """
<PubmedArticle>
  <MedlineCitation>
    <PMID>99999999</PMID>
    <Article>
      <Journal><Title>Test J</Title>
        <JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue></Journal>
      <ArticleTitle>An article whose doi is an ELocationID</ArticleTitle>
      <ELocationID EIdType="doi" ValidYN="Y">10.1000/elocation-own</ELocationID>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ReferenceList>
      <Reference><ArticleIdList>
        <ArticleId IdType="doi">10.9999/reference-only</ArticleId></ArticleIdList></Reference>
    </ReferenceList>
  </PubmedData>
</PubmedArticle>
"""

# No article doi anywhere; only a reference has one. Must NOT leak it.
ARTICLE_WITH_ONLY_REFERENCE_DOI = """
<PubmedArticle>
  <MedlineCitation>
    <PMID>88888888</PMID>
    <Article>
      <Journal><Title>Test J</Title>
        <JournalIssue><PubDate><Year>2019</Year></PubDate></JournalIssue></Journal>
      <ArticleTitle>An article with no doi of its own</ArticleTitle>
    </Article>
  </MedlineCitation>
  <PubmedData>
    <ArticleIdList><ArticleId IdType="pubmed">88888888</ArticleId></ArticleIdList>
    <ReferenceList>
      <Reference><ArticleIdList>
        <ArticleId IdType="doi">10.9999/reference-only</ArticleId></ArticleIdList></Reference>
    </ReferenceList>
  </PubmedData>
</PubmedArticle>
"""


def test_doi_is_article_not_reference():
    rec = _parse_article(ET.fromstring(ARTICLE_WITH_REFERENCE_DOIS))
    assert rec is not None
    assert rec["doi"] == "10.1086/421054"


def test_doi_from_elocation_id():
    rec = _parse_article(ET.fromstring(ARTICLE_WITH_ELOCATION_DOI))
    assert rec is not None
    assert rec["doi"] == "10.1000/elocation-own"


def test_reference_doi_does_not_leak_when_article_has_none():
    rec = _parse_article(ET.fromstring(ARTICLE_WITH_ONLY_REFERENCE_DOI))
    assert rec is not None
    assert rec["doi"] == ""
