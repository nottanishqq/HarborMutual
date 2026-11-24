-- Kept apart from harbor.surql because `surreal export` redacts the JWT key,
-- so this is re-applied after every import. One line: `surreal sql` reads stdin line by line.
DEFINE ACCESS OVERWRITE adjuster ON DATABASE TYPE RECORD SIGNIN (SELECT * FROM adjuster WHERE email = $email AND crypto::argon2::compare(pass, $pass)) DURATION FOR TOKEN 1h, FOR SESSION 1d;
