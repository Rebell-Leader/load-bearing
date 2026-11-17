CREATE RANGE INDEX `manuscript_id` FOR (n:`Manuscript`) ON (n.`id`);
CREATE RANGE INDEX `paper_doi` FOR (n:`Paper`) ON (n.`doi`);
CREATE FULLTEXT INDEX `paper_title` FOR (n:`Paper`) ON EACH [n.`title`] OPTIONS {indexConfig: {`fulltext.analyzer`: 'standard-no-stop-words',`fulltext.eventually_consistent`: false}};
CREATE VECTOR INDEX `paper_vec` FOR (n:`Paper`) ON (n.`vec`) OPTIONS {indexConfig: {`vector.default_search_expansion_factor`: 3.0,`vector.dimensions`: 32,`vector.hnsw.ef_construction`: 100,`vector.hnsw.m`: 16,`vector.quantization.type`: 'BINARY',`vector.similarity_function`: 'COSINE'}};
CREATE CONSTRAINT `claim_id` FOR (n:`Claim`) REQUIRE (n.`id`) IS UNIQUE;
CREATE CONSTRAINT `disposition_id` FOR (n:`Disposition`) REQUIRE (n.`id`) IS UNIQUE;
CREATE CONSTRAINT `notice_id` FOR (n:`Notice`) REQUIRE (n.`id`) IS UNIQUE;
CREATE CONSTRAINT `paper_id` FOR (n:`Paper`) REQUIRE (n.`id`) IS UNIQUE;
