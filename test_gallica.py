"""
test_gallica.py
Offline checks for gallica_harvester.py.

These tests deliberately use XML COPIED FROM A REAL GALLICA RESPONSE, not XML I
composed to match my parser. The difference is the whole point. The Freesound paging
bug passed a test because the mock's fake "next" URL carried a token the real API
strips, so the test proved my belief rather than the API's behaviour.

Real bytes in, or the test is decoration.

Run: python test_gallica.py
"""

import gallica_harvester as gh
import xml.etree.ElementTree as ET

# Verbatim from https://gallica.bnf.fr/SRU?operation=searchRetrieve&version=1.2
#   &maximumRecords=1&query=(gallica all "Archives de la Parole") and dc.type all "sonore"
REAL_RESPONSE = """<srw:searchRetrieveResponse
 xmlns:diag="http://www.loc.gov/zing/srw/diagnostic/"
 xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
 xmlns:srw="http://www.loc.gov/zing/srw/"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
<srw:version>1.2</srw:version>
<srw:numberOfRecords>2265</srw:numberOfRecords>
<srw:records><srw:record><srw:recordData><oai_dc:dc>
<dc:date>191.</dc:date>
<dc:description>[Traditions. Asie. Russie]</dc:description>
<dc:format>1 disque : 88 t ; 29 cm</dc:format>
<dc:format>disc</dc:format>
<dc:identifier>https://gallica.bnf.fr/ark:/12148/bpt6k127626d</dc:identifier>
<dc:identifier>NUMAUD-127626</dc:identifier>
<dc:identifier>50192 G.R, 50281 G.RPat&#233;</dc:identifier>
<dc:language>rus</dc:language>
<dc:rights>domaine public</dc:rights>
<dc:rights>public domain</dc:rights>
<dc:source>Biblioth&#232;que nationale de France, d&#233;partement Audiovisuel, AP-328</dc:source>
<dc:subject>musique traditionnelle &#233;trang&#232;re</dc:subject>
<dc:title>[Archives de la Parole]. , V lesu ; Sumrak no&#269;i / Isp. vokal'nyj kvintet, groupe vocal</dc:title>
<dc:type>sound</dc:type>
</oai_dc:dc></srw:recordData></srw:record></srw:records>
</srw:searchRetrieveResponse>"""

failures = []


def check(label, got, want):
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: got {got!r}, wanted {want!r}")
        failures.append(label)


print("parsing a real SRU response")
root = ET.fromstring(REAL_RESPONSE)
check("total is read", int(root.find("srw:numberOfRecords", gh.NS).text), 2265)

record = root.find(".//srw:record", gh.NS)
fields = gh.dc_fields(record)

# Repeated elements must survive as lists. Keeping only the first identifier would
# throw away "50192 G.R, 50281 G.R Pathe", which is the matrix number, which is how
# a disc with no printed year gets dated.
check("identifier keeps all 3", len(fields["identifier"]), 3)
check("format keeps both", len(fields["format"]), 2)
check("rights keeps both", len(fields["rights"]), 2)
check("single field is still a list", fields["language"], ["rus"])
check("ark extracted", gh.ark_of(fields), "ark:/12148/bpt6k127626d")

print("\ndating from Gallica's dot notation")
check("exact year", gh.decade_of(["1913"]), "1910s (exact year known)")
check("uncertain decade", gh.decade_of(["191."]), "1910s")
check("century only", gh.decade_of(["19.."]), "1900s (century only)")
check("missing", gh.decade_of([]), "no date")
# "before 1939" is the shape that fooled us on the Husseyni disc: an upper bound
# derived from a performer's death, not a date. It must NOT parse as a year.
check("prose is not a year", gh.decade_of(["before 1939"]), "no date")

print("\nthe query keeps its audio-only half")
check("dc.type constraint present", 'dc.type all "sonore"' in gh.COLLECTION_QUERY, True)

print("\npage size stays within Gallica's cap")
check("page size <= 50", gh.PAGE_SIZE <= 50, True)

print()
if failures:
    raise SystemExit(f"{len(failures)} check(s) failed: {failures}")
print("all checks passed")
