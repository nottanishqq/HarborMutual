-- Harbor Mutual on SurrealDB v4: documents, graph, full text and vectors in one schema.
-- Region rule: an adjuster (record user) only ever sees claims from their own region.
-- The rule lives in the database, so the API and the AI agent cannot leak across regions.

DEFINE ANALYZER OVERWRITE en TOKENIZERS class FILTERS lowercase, snowball(english);

DEFINE TABLE OVERWRITE adjuster SCHEMAFULL
    PERMISSIONS FOR select WHERE id = $auth.id;
DEFINE FIELD OVERWRITE name ON adjuster TYPE string;
DEFINE FIELD OVERWRITE email ON adjuster TYPE string;
DEFINE FIELD OVERWRITE region ON adjuster TYPE 'North' | 'South';
DEFINE FIELD OVERWRITE pass ON adjuster TYPE string PERMISSIONS FOR select NONE;
DEFINE INDEX OVERWRITE adjuster_email ON adjuster FIELDS email UNIQUE;

DEFINE TABLE OVERWRITE customer SCHEMAFULL
    PERMISSIONS FOR select WHERE region = $auth.region;
DEFINE FIELD OVERWRITE name ON customer TYPE string;
DEFINE FIELD OVERWRITE email ON customer TYPE string;
DEFINE FIELD OVERWRITE phone ON customer TYPE string;
DEFINE FIELD OVERWRITE region ON customer TYPE 'North' | 'South';

DEFINE TABLE OVERWRITE policy SCHEMAFULL
    PERMISSIONS FOR select WHERE customer.region = $auth.region;
DEFINE FIELD OVERWRITE customer ON policy TYPE record<customer>;
DEFINE FIELD OVERWRITE kind ON policy TYPE 'home' | 'car';
DEFINE FIELD OVERWRITE start_date ON policy TYPE datetime;
DEFINE FIELD OVERWRITE premium ON policy TYPE decimal;
-- Migrated from the Mongo policy_docs collection: free-form, so stored as an object.
DEFINE FIELD OVERWRITE terms ON policy TYPE option<object> FLEXIBLE;

DEFINE TABLE OVERWRITE claim SCHEMAFULL
    PERMISSIONS FOR select WHERE region = $auth.region;
DEFINE FIELD OVERWRITE number ON claim TYPE string;
DEFINE FIELD OVERWRITE policy ON claim TYPE record<policy>;
DEFINE FIELD OVERWRITE adjuster ON claim TYPE record<adjuster>;
DEFINE FIELD OVERWRITE region ON claim TYPE 'North' | 'South';
DEFINE FIELD OVERWRITE status ON claim TYPE 'open' | 'approved' | 'rejected';
DEFINE FIELD OVERWRITE amount ON claim TYPE decimal ASSERT $value > 0;
DEFINE FIELD OVERWRITE filed_at ON claim TYPE datetime;
DEFINE FIELD OVERWRITE description ON claim TYPE string;
-- Payments were a child table in Postgres; they are only ever read with their claim, so they are embedded.
DEFINE FIELD OVERWRITE payments ON claim TYPE array<object> DEFAULT [];
DEFINE FIELD OVERWRITE payments[*].amount ON claim TYPE decimal;
DEFINE FIELD OVERWRITE payments[*].paid_at ON claim TYPE datetime;
DEFINE FIELD OVERWRITE embedding ON claim TYPE array<float>;
DEFINE INDEX OVERWRITE claim_number ON claim FIELDS number UNIQUE;
DEFINE INDEX OVERWRITE claim_region_status ON claim FIELDS region, status;
DEFINE INDEX OVERWRITE claim_text ON claim FIELDS description FULLTEXT ANALYZER en BM25;
DEFINE INDEX OVERWRITE claim_vec ON claim FIELDS embedding HNSW DIMENSION 384 DIST COSINE;

-- People around a claim (witnesses, repair shops, doctors). Shared parties are how fraud rings show up.
DEFINE TABLE OVERWRITE party SCHEMAFULL PERMISSIONS FOR select FULL;
DEFINE FIELD OVERWRITE name ON party TYPE string;
DEFINE FIELD OVERWRITE phone ON party TYPE string;
DEFINE FIELD OVERWRITE kind ON party TYPE 'person' | 'repair_shop' | 'clinic';

-- Many-to-many with a property (role), so it is a graph edge, not a record link.
DEFINE TABLE OVERWRITE involved_in TYPE RELATION IN party OUT claim ENFORCED SCHEMAFULL
    PERMISSIONS FOR select WHERE out.region = $auth.region;
DEFINE FIELD OVERWRITE role ON involved_in TYPE 'witness' | 'repairer' | 'treating_clinic' | 'third_party';
DEFINE INDEX OVERWRITE involved_unique ON involved_in FIELDS in, out UNIQUE;

-- Correspondence, migrated from MongoDB (the Cosmos DB stand-in).
DEFINE TABLE OVERWRITE note SCHEMAFULL
    PERMISSIONS FOR select WHERE claim.region = $auth.region;
DEFINE FIELD OVERWRITE claim ON note TYPE record<claim>;
DEFINE FIELD OVERWRITE channel ON note TYPE 'email' | 'phone' | 'letter';
DEFINE FIELD OVERWRITE author ON note TYPE string;
DEFINE FIELD OVERWRITE body ON note TYPE string;
DEFINE FIELD OVERWRITE sent_at ON note TYPE datetime;
DEFINE INDEX OVERWRITE note_claim ON note FIELDS claim;

-- Agent long-term memory, private to each adjuster.
DEFINE TABLE OVERWRITE memory SCHEMAFULL
    PERMISSIONS FOR select, create WHERE adjuster = $auth.id;
DEFINE FIELD OVERWRITE adjuster ON memory TYPE record<adjuster> DEFAULT $auth.id;
DEFINE FIELD OVERWRITE text ON memory TYPE string;
DEFINE FIELD OVERWRITE embedding ON memory TYPE array<float>;
DEFINE FIELD OVERWRITE at ON memory TYPE datetime DEFAULT time::now();
DEFINE INDEX OVERWRITE memory_vec ON memory FIELDS embedding HNSW DIMENSION 384 DIST COSINE;
