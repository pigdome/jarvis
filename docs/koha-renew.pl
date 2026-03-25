use strict;
use warnings;

use C4::Context;
use C4::Circulation;

my $dd_from = shift;
my $dd_to = shift;

unless ($dd_from and $dd_to) {
    die "[USAGE] $0 [date_due in YYYY-MM-DD] [date_due in YYYY-MM-DD]";
}
my $query = <<END;
SELECT *
FROM issues
LEFT JOIN borrowers USING(borrowernumber)
WHERE date_due >= ?
AND date_due <= ?
END
my $issues = C4::Context->dbh->selectall_arrayref($query, {Slice => {}}, ($dd_from, $dd_to));

printf qq|Issues found %s\n|, scalar @$issues;

foreach my $issue (@$issues) {
    my $date_due = AddRenewal(
        $issue->{borrowernumber},
        $issue->{itemnumber},
        $issue->{branchcode}
    );
    printf qq|[RENEW] {%s} (%s)(%s)(%s) from '%s' to '%s'\n|,
        $issue->{cardnumber},
        $issue->{borrowernumber},
        $issue->{itemnumber},
        $issue->{branchcode},
        $issue->{date_due},
        $date_due;
    sleep 5;
}
