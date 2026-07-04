DOCNAME=main
TEMPLATE_URL=https://cms-resources.apps.public.k8s.springernature.io/springer-cms/rest/v1/content/18782940/data/v12

all: report

.PHONY: clean distclean

template.zip:
	curl -L -o template.zip $(TEMPLATE_URL)
	unzip -jo template.zip 'sn-jnl.cls' 'sn-apacite.bst'

report: template.zip
	pdflatex $(DOCNAME).tex
	bibtex $(DOCNAME).aux
	pdflatex $(DOCNAME).tex
	pdflatex $(DOCNAME).tex
	@echo "Word Count:"
	detex $(DOCNAME).tex | wc -w

view: report
	open $(DOCNAME).pdf

clean:
	rm -f *.blg *.bbl *.aux *.log *.spl

distclean: clean
	rm -f elsarticle.zip elsarticle.cls elsarticle.ins elsarticle.dtx \
	      elsarticle-harv.bst elsarticle-num.bst elsarticle-num-names.bst