import csv
import sqlalchemy
from dnascissors.config import cfg
from dnascissors.model import Base
from shutil import copyfile
import log as logger
import amplifind


def create_files(session, refgenome, project, seq_dict):
    amplicon_file = "amplicons.txt"
    target_file = "targets.txt"
    amplicount_file = "amplicount_config.csv"

    copyfile(seq_dict, amplicon_file)
    copyfile(seq_dict, target_file)

    with open(amplicon_file, "a") as amplicon_output, open(target_file, "a") as target_output, open(amplicount_file, "w") as amplicount_output:
        amplicount_output.write("id,fprimer,rprimer,amplicon\n")

        i = 0
        amplifind_amplicon_desc_list = []
        for amplicon in amplifind.get_amplicons(session, project):
            i += 1
            amplifind_amplicon = amplifind.find_amplicon_sequence(refgenome, amplicon['guide_loc'], amplicon['chr'], amplicon['strand'], amplicon['fprimer_seq'], amplicon['rprimer_seq'])
            amplifind.print_amplifind_report(i, amplicon, amplifind_amplicon)
            # remove duplicated amplicons
            if not amplifind_amplicon['desc'] in amplifind_amplicon_desc_list:
                amplifind_amplicon_desc_list.append(amplifind_amplicon['desc'])
                amplicon_output.write("{}\n".format(amplifind_amplicon['coord']))
                target_output.write("{}\n".format(amplifind_amplicon['target_coord']))
                amplicount_output.write("chr{}_{},{},{},{}\n".format(amplicon['chr'], amplifind_amplicon['start'], amplifind_amplicon['fprimer_seq'], amplifind_amplicon['rprimer_seq'], amplifind_amplicon['seq']))


def filelist_to_text(filelist):
    samples = dict()
    with open(filelist, "r") as input:
        reader = csv.reader(input)
        next(reader)  # Skip header line.
        for line in reader:
            match = samples.get(line[0])
            if match is not None:
                if match != line[2]:
                    print("Sample {} is present with differing barcodes.".format(line[0]))
            samples[line[0]] = line[2]

    with open("samples.txt", "w") as out:
        out.write("Barcode\tSample\n")
        for sample, barcode in samples.items():
            out.write(barcode)
            out.write('\t')
            out.write(sample)
            out.write('\n')


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", dest="project", action="store", help="The project id.", required=True)
    parser.add_argument("--genome", dest="refgenome", action="store", help="The reference genome fasta file e.g. 'hsa.GRCh38_hs38d1.fa'", required=True)
    parser.add_argument("--seq-dict", dest="dict", action="store", help="The reference sequence dictionary. Needed to produce amplicons.txt and targets.txt", required=False)
    parser.add_argument("--filelist", dest="filelist", action="store", help="The file list CSV. Converts into samples.txt", required=False)
    options = parser.parse_args()

    log = logger.get_custom_logger(os.path.join(os.path.dirname(__file__), 'create_pipeline_files.log'))

    engine = sqlalchemy.create_engine(cfg['DATABASE_URI'])
    Base.metadata.bind = engine
    DBSession = sqlalchemy.orm.sessionmaker(bind=engine)
    session = DBSession()

    try:
        if options.dict:
            create_files(session, options.refgenome, options.project, options.dict)
        if options.filelist:
            filelist_to_text(options.filelist)

        session.commit()
    except Exception as e:
        log.exception(e)
        session.rollback()
    finally:
        session.close()


if __name__ == '__main__':
    main()
