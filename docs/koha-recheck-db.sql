SELECT "biblio" AS tablename, COUNT(*) AS count FROM biblio
UNION
SELECT "auth_header" AS tablename, COUNT(*) AS count FROM auth_header
UNION
SELECT "items" AS tablename, COUNT(*) AS count FROM items
UNION
SELECT "borrowers" AS tablename, COUNT(*) AS count FROM borrowers
UNION
SELECT "issues" AS tablename, COUNT(*) AS count FROM issues
UNION
SELECT "old_issues" AS tablename, COUNT(*) AS count FROM old_issues
UNION
SELECT "statistics" AS tablename, COUNT(*) AS count FROM statistics
UNION
SELECT "action_logs" AS tablename, COUNT(*) AS count FROM action_logs
