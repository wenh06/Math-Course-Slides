# vim: set ft=perl:
$ENV{'TZ'}='Asia/Shanghai';
$pdf_mode = 5;
$dvi_mode = 0;
$postscript_mode = 0;
# In latexmk 4.83+, bare names in $clean_ext are literal globs, not extensions.
# Use %R.EXT so they expand to $JOBNAME.EXT (e.g. %R.bbl -> main.bbl).
$clean_ext = '%R.thm %R.glo %R.gls %R.bbl %R.hd %R.loe %R.synctex.gz %R.run.xml %R.bcf %R.run %R.vrb %R.tdo %R-blx.bib %R.toe %R.fls %R.spl %R.nav %R.snm %R.4tc %R.xref %R.tmp %R.4ct %R.idv %R.lg %R.gnuplot %R.table xelatex*.fls *.tex.bak';

# Explicitly use biber for biblatex (auto-detected via .bcf, but made explicit here)
$biber = 'biber %O %S';
