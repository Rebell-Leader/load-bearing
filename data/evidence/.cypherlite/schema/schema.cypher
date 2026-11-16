CREATE FULLTEXT INDEX `paper_title` FOR (n:`Paper`) ON EACH [n.`title`] OPTIONS {indexConfig: {`fulltext.analyzer`: 'standard-no-stop-words',`fulltext.eventually_consistent`: false}};
CREATE CONSTRAINT `notice_id` FOR (n:`Notice`) REQUIRE (n.`id`) IS UNIQUE;
CREATE CONSTRAINT `paper_id` FOR (n:`Paper`) REQUIRE (n.`id`) IS UNIQUE;
