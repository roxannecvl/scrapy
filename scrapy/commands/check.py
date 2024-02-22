import time
from collections import defaultdict
from unittest import TextTestResult as _TextTestResult
from unittest import TextTestRunner

from scrapy.commands import ScrapyCommand
from scrapy.contracts import ContractsManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.misc import load_object, set_environ

class Coverage :

    coverage_matrix = [False] * 11

    def get_coverage_process_response(self) : 
        return self.coverage_matrix
    
class TextTestResult(_TextTestResult):


    
    
    def printSummary(self, start, stop):
        write = self.stream.write
        writeln = self.stream.writeln

        run = self.testsRun
        plural = "s" if run != 1 else ""

        writeln(self.separator2)
        writeln(f"Ran {run} contract{plural} in {stop - start:.3f}s")
        writeln()

        infos = []
        if not self.wasSuccessful():
            write("FAILED")
            failed, errored = map(len, (self.failures, self.errors))
            if failed:
                infos.append(f"failures={failed}")
            if errored:
                infos.append(f"errors={errored}")
        else:
            write("OK")

        if infos:
            writeln(f" ({', '.join(infos)})")
        else:
            write("\n")


class Command(ScrapyCommand):
    requires_project = True
    default_settings = {"LOG_ENABLED": False}

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Check spider contracts"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_argument(
            "-l",
            "--list",
            dest="list",
            action="store_true",
            help="only list contracts, without checking them",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            dest="verbose",
            default=False,
            action="store_true",
            help="print contract tests for all spiders",
        )

    def run(self, args, opts):
        # load contracts
        contracts = build_component_list(self.settings.getwithbase("SPIDER_CONTRACTS"))
        conman = ContractsManager(load_object(c) for c in contracts)
        runner = TextTestRunner(verbosity=2 if opts.verbose else 1) #1-2
        if(opts.verbose) :
            Coverage.coverage_matrix[0] = True
        else :
            Coverage.coverage_matrix[1] = True    
        result = TextTestResult(runner.stream, runner.descriptions, runner.verbosity)

        # contract requests
        contract_reqs = defaultdict(list)

        spider_loader = self.crawler_process.spider_loader

        with set_environ(SCRAPY_CHECK="true"):
            for spidername in args or spider_loader.list(): #3
                Coverage.coverage_matrix[2] = True
                spidercls = spider_loader.load(spidername)
                spidercls.start_requests = lambda s: conman.from_spider(s, result)

                tested_methods = conman.tested_methods_from_spidercls(spidercls)
                if opts.list: #4
                    Coverage.coverage_matrix[3] = True
                    for method in tested_methods: #5
                        Coverage.coverage_matrix[4] = True
                        contract_reqs[spidercls.name].append(method)
                elif tested_methods: #6
                    Coverage.coverage_matrix[5] = True
                    self.crawler_process.crawl(spidercls)

            # start checks
            if opts.list: #7
                Coverage.coverage_matrix[6] = True
                for spider, methods in sorted(contract_reqs.items()): #8
                    Coverage.coverage_matrix[7] = True
                    if not methods and not opts.verbose: #9
                        Coverage.coverage_matrix[8] = True 
                        continue
                    print(spider)
                    for method in sorted(methods): #10
                        Coverage.coverage_matrix[9] = True
                        print(f"  * {method}")
            else: #11
                Coverage.coverage_matrix[10] = True
                start = time.time()
                self.crawler_process.start()
                stop = time.time()

                result.printErrors()
                result.printSummary(start, stop)
                self.exitcode = int(not result.wasSuccessful())

            #CCN = 11 +2 = 13


   