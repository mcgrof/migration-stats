all: plot

.PHONY: example

example:
	tar -xJf example-0001.tar.xz
	cp example-0001/*stats.txt .

plot: ./plot_migration_stats.py *.stats.txt
	./plot_migration_stats.py *.stats.txt

clean:
	rm -rf *.png *.stats.txt example-0001
