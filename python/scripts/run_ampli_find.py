import sqlalchemy
from dnascissors.config import cfg
from dnascissors.model import Base
from dnascissors.model import Primer
from dnascissors.model import AmpliconSelection
from dnascissors.model import Guide
from dnascissors.model import Target
from dnascissors.model import Project
from dnascissors.model import SequencingLibraryContent
from dnascissors.model import Well
from dnascissors.model import ExperimentLayout
import requests
import json
from Bio.Seq import Seq
from Bio.Alphabet import IUPAC
from pyfaidx import Fasta

REST_ENSEMBL_URL = "http://rest.ensembl.org"


def get_samples(dbsession, refgenome, geid):
    results = []
    seqlib_contents = dbsession.query(SequencingLibraryContent)\
                               .join(SequencingLibraryContent.well)\
                               .join(Well.well_content)\
                               .join(Well.experiment_layout)\
                               .join(ExperimentLayout.project)\
                               .filter(Project.geid == geid)\
                               .all()
    for seqlib_content in seqlib_contents:
        for guide in seqlib_content.well.well_content.guides:
            for amplicon_selection in guide.amplicon_selections:
                if amplicon_selection.is_on_target:
                    primers = [p for p in dbsession.query(Primer).all() if amplicon_selection.amplicon in p.amplicons]
                    for primer in primers:
                        if primer.strand == 'forward':
                            fprimer_seq = primer.sequence
                        elif primer.strand == 'reverse':
                            rprimer_seq = primer.sequence
                    direction = '0'
                    if amplicon_selection.guide_strand == 'reverse':
                        direction = '1'
                    guide_loc = get_guide_location(geid, int(amplicon_selection.amplicon.chromosome), int(amplicon_selection.guide_location), fprimer_seq)
                    amplifind = find_amplicon_sequence(refgenome, guide_loc, amplicon_selection.amplicon.chromosome, amplicon_selection.guide_strand, fprimer_seq, rprimer_seq)
                    fprimer = amplifind['fprimer_seq']
                    rprimer = amplifind['rprimer_seq']
                    seq = amplifind['seq']
                    if (geid == 'GEP00001') and (int(amplicon_selection.amplicon.chromosome) == 17):
                        fprimer_ori = fprimer
                        fprimer = str(Seq(rprimer, IUPAC.unambiguous_dna).reverse_complement())
                        rprimer = str(Seq(fprimer_ori, IUPAC.unambiguous_dna).reverse_complement())
                        seq = str(Seq(seq, IUPAC.unambiguous_dna).reverse_complement())
                    results.append({'name': seqlib_content.sequencing_sample_name,
                                    'barcode': seqlib_content.sequencing_barcode,
                                    'guide': guide.guide_sequence,
                                    'fprimer': fprimer,
                                    'rprimer': rprimer,
                                    'direction': direction,
                                    'amplicon': seq})
    return results


def get_guide_location(geid, chr, guide_loc, fprimer_seq):
    if geid == 'GEP00001':
        if chr == 17 and guide_loc == 40498696:
            return 42346600
        elif chr == 1 and guide_loc == 44880935 and fprimer_seq == 'CAGGCCCAACACAGAGATACTTT':
            return 112448940
        elif chr == 19 and guide_loc == 56539112:
            return 56027650
        elif chr == 17 and guide_loc == 40497587:
            return 42345525
        elif chr == 10 and guide_loc == 50174690:
            return 48966575
        elif chr == 15 and guide_loc == 89399516:
            return 88856000
        elif chr == 17 and guide_loc == 40497619:
            return 42345525
        elif chr == 12 and guide_loc == 125765689:
            return 125281040
        elif chr == 1 and guide_loc == 44880935 and fprimer_seq == 'GACGTGTGTCGGAATATTTATGGT':
            return 44415190
        elif chr == 17 and guide_loc == 40497633:
            return 42345525
    return guide_loc


def get_amplicons(dbsession, geid):
    amplicons = []
    amplicon_selections = dbsession.query(AmpliconSelection)\
                                   .join(AmpliconSelection.guide)\
                                   .join(Guide.target)\
                                   .join(Target.project)\
                                   .filter(Project.geid == geid)\
                                   .all()
    # Should do this as another query with IN [amplicon.in_(Primer.amplicons], but it doesn't seem to work.
    primers = dbsession.query(Primer).all()
    for amplicon_selection in amplicon_selections:
        amplicon = amplicon_selection.amplicon
        aprimers = [p for p in primers if amplicon in p.amplicons]
        for primer in aprimers:
            if primer.strand == 'forward':
                fprimer_seq = primer.sequence
                tstart = primer.end + 1
            elif primer.strand == 'reverse':
                rprimer_seq = primer.sequence
                tend = primer.start - 1
        # Add strand information from guide, will not work of multiple guides!
        strand = '+'
        if amplicon_selection.guide_strand == 'reverse':
            strand = '-'
        acoord = "chr{}\t{}\t{}\t{}\t{}".format(amplicon.chromosome,
                                                amplicon.start,
                                                amplicon.end,
                                                strand,
                                                "chr{}_{}".format(amplicon.chromosome, amplicon.start))

        tcoord = "chr{}\t{}\t{}\t{}\t{}".format(amplicon.chromosome,
                                                tstart,
                                                tend,
                                                strand,
                                                "chr{}_{}".format(amplicon.chromosome, amplicon.start))
        amplicon_result = {'gene_id': amplicon_selection.guide.target.gene_id,
                           'fprimer_seq': fprimer_seq,
                           'rprimer_seq': rprimer_seq,
                           'guide_loc': amplicon_selection.guide_location,
                           'strand': strand,
                           'chr': int(amplicon.chromosome),
                           'amplicon_coord': acoord,
                           'amplicon_len': amplicon.end-amplicon.start+1,
                           'target_coord': tcoord,
                           'target_len': tend-tstart+1,
                           'target_name': amplicon_selection.guide.target.name}
        amplicon_result['guide_loc'] = get_guide_location(geid, amplicon_result['chr'], amplicon_result['guide_loc'], amplicon_result['fprimer_seq'])
        amplicons.append(amplicon_result)
    return amplicons


def find_primer(sequence, primer_seq):
    primer_seq_ori = primer_seq
    primer_loc = sequence.find(primer_seq)
    if primer_loc == -1:
        primer_seq = str(Seq(primer_seq, IUPAC.unambiguous_dna).reverse_complement())
        primer_loc = sequence.find(primer_seq)
    return primer_loc, primer_seq, primer_seq_ori


def get_primer_pair(sequence, fprimer_seq, rprimer_seq):
    fprimer_loc, fprimer_seq, fprimer_seq_ori = find_primer(sequence, fprimer_seq)
    rprimer_loc, rprimer_seq, rprimer_seq_ori = find_primer(sequence, rprimer_seq)
    return fprimer_loc, fprimer_seq, rprimer_loc, rprimer_seq


def find_amplicon_sequence_ensembl(ensembl_gene_id, fprimer_seq, rprimer_seq):
    # retrieve gene sequence
    url = "{}/sequence/id/{}?species={}".format(REST_ENSEMBL_URL, ensembl_gene_id, 'homo_sapiens')
    r = requests.get(url, headers={"Content-Type": "application/json"})
    gene = json.loads(r.text)
    sequence = gene['seq']
    text, assembly, chr, start, end, strand = gene['desc'].split(':')
    strand = ('+' if strand == '1' else '-')

    fprimer_loc, fprimer_seq, rprimer_loc, rprimer_seq = get_primer_pair(sequence, fprimer_seq, rprimer_seq)

    if fprimer_loc > rprimer_loc:
        fprimer_loc, fprimer_seq, rprimer_loc, rprimer_seq = get_primer_pair(sequence, rprimer_seq, fprimer_seq)

    amplicon_seq = sequence[fprimer_loc:(rprimer_loc + len(rprimer_seq))]
    amplicon_start = int(start) + fprimer_loc - 1
    amplicon_end = int(start) + (rprimer_loc + len(rprimer_seq) - 1)
    amplicon_desc = "{}:chr{}:{}:{}:{}".format(assembly, chr, amplicon_start, amplicon_end, strand)
    acoord = "chr{}\t{}\t{}\t{}\t{}".format(chr,
                                            amplicon_start,
                                            amplicon_end,
                                            strand,
                                            "{}_chr{}_{}".format(assembly, chr, amplicon_start))

    target_start = int(start) + (fprimer_loc + len(fprimer_seq) - 1)
    target_end = int(start) + rprimer_loc - 1
    tcoord = "chr{}\t{}\t{}\t{}\t{}".format(chr,
                                            target_start,
                                            target_end,
                                            strand,
                                            "{}_chr{}_{}".format(assembly, chr, amplicon_start))
    amplicon = {'gene_id': ensembl_gene_id,
                'fprimer_loc': fprimer_loc,
                'fprimer_seq': fprimer_seq,
                'rprimer_loc': rprimer_loc,
                'rprimer_seq': rprimer_seq,
                'seq': amplicon_seq,
                'start': amplicon_start,
                'end': amplicon_end,
                'desc': amplicon_desc,
                'coord': acoord,
                'target_coord': tcoord}
    return amplicon


def find_amplicon_sequence(refgenome, guide_loc, chr, strand, fprimer_seq, rprimer_seq):
    # retrieve amplicon sequence +/- 1000 around guide location
    start = guide_loc - 1000
    sequence = Fasta(refgenome)['chr{}'.format(chr)][start:guide_loc+1000].seq

    fprimer_loc, fprimer_seq, rprimer_loc, rprimer_seq = get_primer_pair(sequence, fprimer_seq, rprimer_seq)

    if fprimer_loc > rprimer_loc:
        fprimer_loc, fprimer_seq, rprimer_loc, rprimer_seq = get_primer_pair(sequence, rprimer_seq, fprimer_seq)

    amplicon_seq = sequence[fprimer_loc:(rprimer_loc + len(rprimer_seq))]
    amplicon_start = int(start) + fprimer_loc + 1
    amplicon_end = int(start) + (rprimer_loc + len(rprimer_seq))
    amplicon_desc = "chr{}:{}:{}".format(chr, amplicon_start, amplicon_end)
    acoord = "chr{}\t{}\t{}\t{}\t{}".format(chr,
                                            amplicon_start,
                                            amplicon_end,
                                            strand,
                                            "chr{}_{}".format(chr, amplicon_start))
    genomic_acoord = "chr{}:{}-{}".format(chr, amplicon_start, amplicon_end)

    target_start = int(start) + (fprimer_loc + len(fprimer_seq)) + 1
    target_end = int(start) + rprimer_loc
    tcoord = "chr{}\t{}\t{}\t{}\t{}".format(chr,
                                            target_start,
                                            target_end,
                                            strand,
                                            "chr{}_{}".format(chr, amplicon_start))
    amplicon = {'fprimer_loc': fprimer_loc,
                'fprimer_seq': fprimer_seq,
                'rprimer_loc': rprimer_loc,
                'rprimer_seq': rprimer_seq,
                'seq': amplicon_seq,
                'start': amplicon_start,
                'end': amplicon_end,
                'desc': amplicon_desc,
                'coord': acoord,
                'gcoord': genomic_acoord,
                'target_coord': tcoord}
    return amplicon


def print_amplifind_report(i, amplicon, amplifind):
    print('--- Amplicon #{}'.format(i))
    print('Target name\t{}'.format(amplicon['target_name']))
    print('Forward primer\t{}'.format(amplifind['fprimer_seq']))
    print('Reverse primer\t{}'.format(amplifind['rprimer_seq']))
    print('target coord\t{}'.format(amplifind['target_coord']))
    print('amplicon coord\t{}'.format(amplifind['coord']))
    print('amplicon desc\t{}'.format(amplifind['desc']))
    print('amplicon seq\t{}'.format(amplifind['seq']))
    print('amplicon seq len\t{}'.format(len(amplifind['seq'])))
    if amplifind['fprimer_loc'] == -1 or amplifind['rprimer_loc'] == -1:
        print('>>> Primers not found! [fprimer: {}, rprimer: {}]'.format(amplifind['fprimer_loc'], amplifind['rprimer_loc']))
    if not amplicon['amplicon_len'] == len(amplifind['seq']):
        print('>>> Amplicon length different than the one submitted. [submitted: {}, found: {}]'.format(amplicon['amplicon_len'], len(amplifind['seq'])))
    if not amplicon['fprimer_seq'] == amplifind['fprimer_seq']:
        print('>>> Forward primer sequence different than the one submitted! [submitted: {}, found: {}]'.format(amplicon['fprimer_seq'], amplifind['fprimer_seq']))
    if not amplicon['rprimer_seq'] == amplifind['rprimer_seq']:
        print('>>> Reverse primer sequence different than the one submitted! [submitted: {}, found: {}]'.format(amplicon['rprimer_seq'], amplifind['rprimer_seq']))
    if not amplicon['amplicon_coord'] == amplifind['coord']:
        print('>>> Amplicon coord different than the one submitted! [submitted: {}, found: {}]'.format(amplicon['amplicon_coord'], amplifind['coord']))
    if not amplicon['target_coord'] == amplifind['target_coord']:
        print('>>> Amplicon coord different than the one submitted! [submitted: {}, found: {}]'.format(amplicon['target_coord'], amplifind['target_coord']))
    print('---')


def main():
    import sys
    geid = sys.argv[1]  # add your GEPID on the command line
    refgenome = sys.argv[2]  # add path to the hsa.GRCh38_hs38d1.fa file
    i = 0
    print('Project ID\t{}'.format(geid))
    engine = sqlalchemy.create_engine(cfg['DATABASE_URI'])
    Base.metadata.bind = engine
    DBSession = sqlalchemy.orm.sessionmaker(bind=engine)
    dbsession = DBSession()
    for amplicon in get_amplicons(dbsession, geid):
        i += 1
        amplifind = find_amplicon_sequence(refgenome, amplicon['guide_loc'], amplicon['chr'], amplicon['strand'], amplicon['fprimer_seq'], amplicon['rprimer_seq'])
        print_amplifind_report(i, amplicon, amplifind)
    dbsession.close()


if __name__ == '__main__':
    main()
