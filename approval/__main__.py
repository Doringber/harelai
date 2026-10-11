"""Usage: python -m approval CASE --language he|en --output-dir runs/NAME."""
import argparse
from pathlib import Path
import sys

from approval.workflow import compare_runs, dump, run_case


def main() -> None:
    parser = argparse.ArgumentParser(description='Configurable document review using local Ollama')
    parser.add_argument('case', nargs='?', default='case.json', type=Path)
    parser.add_argument('--model', default='gemma4')
    parser.add_argument('--profile', help='built-in profile name or JSON path (relative to current directory)')
    parser.add_argument('--language', choices=['he', 'en'], default='he', help='output language; source quotes stay verbatim')
    parser.add_argument('--output', type=Path, help='result JSON path; default result.json if no --output-dir')
    parser.add_argument('--output-dir', type=Path, help='empty directory for result and complete run artifacts')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--chunk-size', type=int, default=6000, help='UTF-8 byte budget, 32–8000')
    parser.add_argument('--ocr', action='store_true', help='read scanned PDF pages with local OCR')
    parser.add_argument('--tessdata', help='directory containing OCR .traineddata files')
    parser.add_argument('--ocr-language', default='eng+heb')
    args = parser.parse_args()
    if args.repeat < 1: parser.error('--repeat must be at least 1')
    if args.repeat > 1 and not args.output_dir: parser.error('--repeat requires --output-dir')
    he = args.language == 'he'
    try:
        if args.repeat > 1:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            if any(args.output_dir.iterdir()): raise ValueError(f'Run directory must be empty: {args.output_dir}')
        results = []
        for number in range(1, args.repeat + 1):
            directory = args.output_dir
            if args.repeat > 1: directory = directory / f'run-{number:02d}'
            print(f'בודק את {args.case} באמצעות {args.model}' if he else f'Reviewing {args.case} with {args.model}')
            result = run_case(args.case, args.model, profile=args.profile, language=args.language,
                              output_dir=directory, ocr=args.ocr, tessdata=args.tessdata,
                              ocr_language=args.ocr_language, chunk_size=args.chunk_size)
            results.append(result)
            print(f"\n{result['recommendation']['status']}: {result['recommendation']['reason']}")
            if directory: print(f'תוצאות ויומנים: {directory}' if he else f'Results and logs: {directory}')
        output = args.output or (Path('result.json') if not args.output_dir else None)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            dump(output, results[-1])
            print(f'התוצאה נשמרה: {output}' if he else f'Result saved: {output}')
        comparison = None
        if args.repeat > 1:
            comparison = compare_runs(results)
            dump(args.output_dir / 'comparison.json', comparison)
            print(('הרצות חוזרות זהות: ' if he else 'Repeat runs stable: ') + str(comparison['stable']))
        failed = any(issue.get('code') in ('document_failed', 'extraction_failed')
                     for result in results for issue in result['issues'])
        if failed:
            print('העיבוד לא הושלם; ראו את פירוט השגיאות בתוצאה.' if he else
                  'Processing did not complete; see the result for the errors.', file=sys.stderr)
            sys.exit(1)
        if comparison is not None and not comparison['stable']: sys.exit(2)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(('שגיאה: ' if he else 'Error: ') + str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
