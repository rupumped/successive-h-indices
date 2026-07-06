DOCNAME=main
OPEN := $(shell grep -qi microsoft /proc/version 2>/dev/null && echo wslview || echo open)
TEMPLATE_URL=https://cms-resources.apps.public.k8s.springernature.io/springer-cms/rest/v1/content/18782940/data/v12

all: report

.PHONY: clean distclean

sn-jnl.cls sn-apacite.bst:
	curl -L -o template.zip $(TEMPLATE_URL)
	unzip -jo template.zip '*/sn-jnl.cls' '*/sn-apacite.bst'
	rm -f template.zip

report: sn-jnl.cls sn-apacite.bst
	pdflatex $(DOCNAME).tex
	bibtex $(DOCNAME).aux
	pdflatex $(DOCNAME).tex
	pdflatex $(DOCNAME).tex
	@echo "Word Count:"
	detex $(DOCNAME).tex | wc -w

view: report
	$(OPEN) $(DOCNAME).pdf

clean:
	rm -f *.blg *.bbl *.aux *.log *.spl

distclean: clean
	rm -f template.zip sn-jnl.cls sn-apacite.bst