const fs = require("fs");
const path = require("path");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  ImageRun,
  Header,
  Footer,
  AlignmentType,
  LevelFormat,
  TableOfContents,
  HeadingLevel,
  BorderStyle,
  WidthType,
  ShadingType,
  PageNumber,
  PageBreak,
} = require("docx");

// === FORMAL Style Preset ===
const S = {
  fonts: { heading: "Arial", body: "Arial" },
  sizes: {
    title: 56,
    h1: 36,
    h2: 28,
    h3: 24,
    body: 22,
    caption: 18, // half-points
  },
  colors: {
    heading: "1B3A5C",
    body: "2C3E50",
    accent: "2E75B6",
    tableBorder: "1B3A5C",
    tableHeaderBg: "1B3A5C",
    tableHeaderText: "FFFFFF",
    tableAltRowBg: "EBF5FB",
  },
  spacing: {
    h1Before: 400,
    h1After: 240,
    h2Before: 280,
    h2After: 160,
    bodyAfter: 140,
    lineSpacing: 288,
  },
};

const PAGE_WIDTH = 11906; // A4
const PAGE_HEIGHT = 16838;
const MARGIN = 1440;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2; // 9026

// === Helper functions ===
function heading(level, text) {
  return new Paragraph({
    heading: level,
    children: [
      new TextRun({
        text,
        font: S.fonts.heading,
        bold: true,
        color: S.colors.heading,
      }),
    ],
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    spacing: { after: S.spacing.bodyAfter, line: S.spacing.lineSpacing },
    children: [
      new TextRun({
        text,
        font: S.fonts.body,
        size: S.sizes.body,
        color: S.colors.body,
        bold: opts.bold || false,
      }),
    ],
  });
}

function bulletItem(text, ref) {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    spacing: { after: 80, line: S.spacing.lineSpacing },
    children: [
      new TextRun({
        text,
        font: S.fonts.body,
        size: S.sizes.body,
        color: S.colors.body,
      }),
    ],
  });
}

const border = {
  style: BorderStyle.SINGLE,
  size: 4,
  color: S.colors.tableBorder,
};
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function headerCell(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: {
      fill: S.colors.tableHeaderBg,
      type: ShadingType.CLEAR,
      color: "auto",
    },
    margins: cellMargins,
    children: [
      new Paragraph({
        children: [
          new TextRun({
            text,
            font: S.fonts.body,
            size: S.sizes.body,
            color: S.colors.tableHeaderText,
            bold: true,
          }),
        ],
      }),
    ],
  });
}

function dataCell(text, width, alt = false) {
  const shading = alt
    ? { fill: S.colors.tableAltRowBg, type: ShadingType.CLEAR, color: "auto" }
    : { fill: "FFFFFF", type: ShadingType.CLEAR, color: "auto" };
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading,
    margins: cellMargins,
    children: [
      new Paragraph({
        children: [
          new TextRun({
            text,
            font: S.fonts.body,
            size: S.sizes.body,
            color: S.colors.body,
          }),
        ],
      }),
    ],
  });
}

function makeTable(headers, rows, colWidths) {
  const totalWidth = colWidths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [
      new TableRow({
        children: headers.map((h, i) => headerCell(h, colWidths[i])),
      }),
      ...rows.map(
        (row, ri) =>
          new TableRow({
            children: row.map((cell, ci) =>
              dataCell(cell, colWidths[ci], ri % 2 === 1),
            ),
          }),
      ),
    ],
  });
}

function imageBlock(filename, caption, widthPt, heightPt) {
  const imgPath = path.join(__dirname, filename);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 200, after: 80 },
      children: [
        new ImageRun({
          type: "png",
          data: fs.readFileSync(imgPath),
          transformation: { width: widthPt, height: heightPt },
          altText: { title: caption, description: caption, name: filename },
        }),
      ],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
      children: [
        new TextRun({
          text: caption,
          font: S.fonts.body,
          size: S.sizes.caption,
          color: S.colors.accent,
          italics: true,
        }),
      ],
    }),
  ];
}

// === Build document ===
async function main() {
  const doc = new Document({
    styles: {
      default: {
        document: {
          run: { font: S.fonts.body, size: S.sizes.body, color: S.colors.body },
        },
      },
      paragraphStyles: [
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: {
            size: S.sizes.h1,
            bold: true,
            font: S.fonts.heading,
            color: S.colors.heading,
          },
          paragraph: {
            spacing: { before: S.spacing.h1Before, after: S.spacing.h1After },
            outlineLevel: 0,
            border: {
              bottom: {
                style: BorderStyle.DOUBLE,
                size: 6,
                color: S.colors.heading,
                space: 4,
              },
            },
          },
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: {
            size: S.sizes.h2,
            bold: true,
            font: S.fonts.heading,
            color: S.colors.heading,
          },
          paragraph: {
            spacing: { before: S.spacing.h2Before, after: S.spacing.h2After },
            outlineLevel: 1,
            border: {
              bottom: {
                style: BorderStyle.SINGLE,
                size: 4,
                color: S.colors.accent,
                space: 2,
              },
            },
          },
        },
        {
          id: "Heading3",
          name: "Heading 3",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: {
            size: S.sizes.h3,
            bold: true,
            italics: true,
            font: S.fonts.heading,
            color: S.colors.heading,
          },
          paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 },
        },
      ],
    },
    numbering: {
      config: [
        {
          reference: "bullets",
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: "\u2022",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: 720, hanging: 360 } } },
            },
          ],
        },
        {
          reference: "numbers",
          levels: [
            {
              level: 0,
              format: LevelFormat.DECIMAL,
              text: "%1.",
              alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: 720, hanging: 360 } } },
            },
          ],
        },
      ],
    },
    sections: [
      // === COVER PAGE ===
      {
        properties: {
          page: {
            size: { width: PAGE_WIDTH, height: PAGE_HEIGHT },
            margin: {
              top: MARGIN,
              bottom: MARGIN,
              left: MARGIN,
              right: MARGIN,
            },
          },
        },
        children: [
          new Paragraph({ spacing: { before: 4000 } }),
          new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { after: 400 },
            children: [
              new TextRun({
                text: "HRMOS\u63A1\u7528 \u5FDC\u52DF\u8005\u66F8\u985EAI\u8A55\u4FA1\u30C4\u30FC\u30EB",
                font: S.fonts.heading,
                size: S.sizes.title,
                bold: true,
                color: S.colors.heading,
              }),
            ],
          }),
          new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { after: 200 },
            border: {
              bottom: {
                style: BorderStyle.DOUBLE,
                size: 6,
                color: S.colors.heading,
                space: 8,
              },
            },
            children: [
              new TextRun({
                text: "\u30D7\u30ED\u30B8\u30A7\u30AF\u30C8\u7DCF\u62EC\u5831\u544A\u66F8",
                font: S.fonts.heading,
                size: S.sizes.h1,
                color: S.colors.accent,
              }),
            ],
          }),
          new Paragraph({ spacing: { before: 600 } }),
          new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({
                text: "2026\u5E743\u67087\u65E5",
                font: S.fonts.body,
                size: S.sizes.h2,
                color: S.colors.body,
              }),
            ],
          }),
        ],
      },
      // === TOC ===
      {
        properties: {
          page: {
            size: { width: PAGE_WIDTH, height: PAGE_HEIGHT },
            margin: {
              top: MARGIN,
              bottom: MARGIN,
              left: MARGIN,
              right: MARGIN,
            },
          },
        },
        headers: {
          default: new Header({
            children: [
              new Paragraph({
                alignment: AlignmentType.RIGHT,
                children: [
                  new TextRun({
                    text: "HRMOS\u63A1\u7528 \u5FDC\u52DF\u8005\u66F8\u985EAI\u8A55\u4FA1\u30C4\u30FC\u30EB",
                    font: S.fonts.body,
                    size: S.sizes.caption,
                    color: S.colors.accent,
                  }),
                ],
              }),
            ],
          }),
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [
                  new TextRun({
                    children: [PageNumber.CURRENT],
                    font: S.fonts.body,
                    size: S.sizes.caption,
                  }),
                ],
              }),
            ],
          }),
        },
        children: [
          heading(HeadingLevel.HEADING_1, "\u76EE\u6B21"),
          new TableOfContents("Table of Contents", {
            hyperlink: true,
            headingStyleRange: "1-3",
          }),
          new Paragraph({ children: [new PageBreak()] }),

          // === 1. PROJECT OVERVIEW ===
          heading(
            HeadingLevel.HEADING_1,
            "1. \u30D7\u30ED\u30B8\u30A7\u30AF\u30C8\u6982\u8981",
          ),
          heading(
            HeadingLevel.HEADING_2,
            "1.1 \u30D7\u30ED\u30B8\u30A7\u30AF\u30C8\u540D\u30FB\u5B9F\u65BD\u671F\u9593",
          ),
          makeTable(
            ["\u9805\u76EE", "\u5185\u5BB9"],
            [
              [
                "\u30D7\u30ED\u30B8\u30A7\u30AF\u30C8\u540D",
                "HRMOS\u63A1\u7528 \u5FDC\u52DF\u8005\u66F8\u985EAI\u8A55\u4FA1\u30C4\u30FC\u30EB",
              ],
              [
                "\u5B9F\u65BD\u671F\u9593",
                "2026\u5E742\u670817\u65E5 \u301C 2026\u5E743\u67087\u65E5\uFF08\u7D043\u9031\u9593\uFF09",
              ],
              ["\u30EA\u30DD\u30B8\u30C8\u30EA", "AGS_HRMOS_AUTO_EVAL"],
              ["\u52D5\u4F5C\u74B0\u5883", "Windows 10/11\u3001Python 3.10+"],
            ],
            [2500, 6526],
          ),

          heading(HeadingLevel.HEADING_2, "1.2 \u80CC\u666F\u3068\u76EE\u7684"),
          body(
            "HRMOS\u63A1\u7528\u30DA\u30FC\u30B8\u306B\u767B\u9332\u3055\u308C\u308B\u5FDC\u52DF\u8005\u306E\u5C65\u6B74\u66F8\u30FB\u8077\u52D9\u7D4C\u6B74\u66F8\u3092\u3001\u4EBA\u4E8B\u62C5\u5F53\u8005\u304C1\u4EF6\u305A\u3064\u78BA\u8A8D\u3057\u3066\u30B9\u30B3\u30A2\u30EA\u30F3\u30B0\u3059\u308B\u4F5C\u696D\u306F\u6642\u9593\u3068\u52B4\u529B\u304C\u304B\u304B\u308A\u3001\u8A55\u4FA1\u306E\u3070\u3089\u3064\u304D\u3082\u751F\u3058\u3084\u3059\u3044\u3002",
          ),
          body(
            "\u672C\u30D7\u30ED\u30B8\u30A7\u30AF\u30C8\u3067\u306F\u3001\u3053\u306E\u66F8\u985E\u8A55\u4FA1\u30D7\u30ED\u30BB\u30B9\u3092AI\uFF08Claude CLI / Gemini CLI\uFF09\u3067\u81EA\u52D5\u5316\u3057\u3001\u4E00\u8CAB\u3057\u305F\u8A55\u4FA1\u57FA\u6E96\u306B\u3088\u308B\u8FC5\u901F\u306A\u30B9\u30AF\u30EA\u30FC\u30CB\u30F3\u30B0\u3092\u5B9F\u73FE\u3059\u308B\u3053\u3068\u3092\u76EE\u7684\u3068\u3057\u305F\u3002",
          ),

          heading(HeadingLevel.HEADING_2, "1.3 \u30B9\u30B3\u30FC\u30D7"),
          heading(HeadingLevel.HEADING_3, "\u5BFE\u8C61\u7BC4\u56F2"),
          bulletItem(
            "HRMOS\u304B\u3089\u306E\u5FDC\u52DF\u8005\u66F8\u985E\u81EA\u52D5\u30C0\u30A6\u30F3\u30ED\u30FC\u30C9\uFF08PDF/Word/Excel\uFF09",
            "bullets",
          ),
          bulletItem(
            "\u8A2D\u5B9A\u53EF\u80FD\u306A\u8A55\u4FA1\u57FA\u6E96\u306B\u57FA\u3065\u304FAI\u30B9\u30B3\u30A2\u30EA\u30F3\u30B0\uFF081\u301C5\u70B9\uFF09",
            "bullets",
          ),
          bulletItem(
            "\u9762\u63A5\u8CEA\u554F\u5019\u88DC\u306E\u81EA\u52D5\u751F\u6210",
            "bullets",
          ),
          bulletItem(
            "\u30EC\u30FC\u30C0\u30FC\u30C1\u30E3\u30FC\u30C8\u30FB\u30E9\u30F3\u30AF\u4ED8\u304DExcel\u30EC\u30DD\u30FC\u30C8\u306E\u81EA\u52D5\u51FA\u529B",
            "bullets",
          ),
          bulletItem(
            "\u30E1\u30FC\u30EB\u901A\u77E5\uFF08Resend API\u3001\u30AA\u30D7\u30B7\u30E7\u30F3\uFF09",
            "bullets",
          ),
          bulletItem(
            "Windows\u30BF\u30B9\u30AF\u30B9\u30B1\u30B8\u30E5\u30FC\u30E9\u306B\u3088\u308B\u5B9A\u671F\u81EA\u52D5\u5B9F\u884C",
            "bullets",
          ),
          heading(HeadingLevel.HEADING_3, "\u5BFE\u8C61\u5916"),
          bulletItem(
            "\u9762\u63A5\u7BA1\u7406\u30FB\u5185\u5B9A\u7BA1\u7406",
            "bullets",
          ),
          bulletItem(
            "HRMOS\u4EE5\u5916\u306E\u63A1\u7528\u7BA1\u7406\u30B7\u30B9\u30C6\u30E0\u3068\u306E\u9023\u643A",
            "bullets",
          ),

          heading(
            HeadingLevel.HEADING_2,
            "1.4 \u4E3B\u8981\u30E6\u30FC\u30B9\u30B1\u30FC\u30B9",
          ),
          makeTable(
            [
              "#",
              "\u30E6\u30FC\u30B9\u30B1\u30FC\u30B9",
              "\u30B3\u30DE\u30F3\u30C9",
              "\u6982\u8981",
            ],
            [
              [
                "1",
                "\u65E5\u6B21\u30B9\u30AD\u30E3\u30F3",
                "python run.py scan",
                "\u65B0\u898F\u5FDC\u52DF\u8005\u306E\u66F8\u985EDL\u2192AI\u8A55\u4FA1\u2192Excel\u51FA\u529B\u3002\u8A55\u4FA1\u6E08\u307F\u306F\u81EA\u52D5\u30B9\u30AD\u30C3\u30D7",
              ],
              [
                "2",
                "\u5168\u4EF6\u518D\u8A55\u4FA1",
                "python run.py scan --all",
                "\u8A55\u4FA1\u57FA\u6E96\u5909\u66F4\u6642\u306B\u5168\u5FDC\u52DF\u8005\u3092\u518D\u30B9\u30B3\u30A2\u30EA\u30F3\u30B0",
              ],
              [
                "3",
                "\u30A8\u30E9\u30FC\u30EA\u30C8\u30E9\u30A4",
                "python run.py scan --retry-errors",
                "LLM\u30BF\u30A4\u30E0\u30A2\u30A6\u30C8\u7B49\u3067\u5931\u6557\u3057\u305F\u5FDC\u52DF\u8005\u306E\u307F\u518D\u51E6\u7406",
              ],
              [
                "4",
                "\u30EC\u30DD\u30FC\u30C8\u518D\u51FA\u529B",
                "python run.py report",
                "DB\u5185\u306E\u8A55\u4FA1\u7D50\u679C\u304B\u3089Excel\u3092\u518D\u751F\u6210",
              ],
              [
                "5",
                "\u5B9A\u671F\u81EA\u52D5\u5B9F\u884C",
                "\u30BF\u30B9\u30AF\u30B9\u30B1\u30B8\u30E5\u30FC\u30E9",
                "\u5E73\u65E5\u306E\u663C\u30FB\u5915\u65B9\u306B\u81EA\u52D5\u3067scan\u3092\u5B9F\u884C",
              ],
            ],
            [400, 1600, 3226, 3800],
          ),

          heading(
            HeadingLevel.HEADING_2,
            "1.5 \u4E3B\u8981\u6210\u679C\u30B5\u30DE\u30EA\u30FC",
          ),
          bulletItem(
            "\u5FDC\u52DF\u8005\u66F8\u985E\u306E\u53D6\u5F97\u304B\u3089\u8A55\u4FA1\u30FB\u30EC\u30DD\u30FC\u30C8\u51FA\u529B\u307E\u3067\u3092\u5B8C\u5168\u81EA\u52D5\u5316",
            "bullets",
          ),
          bulletItem(
            "\u30AB\u30B9\u30BF\u30DE\u30A4\u30BA\u53EF\u80FD\u306A\u8A55\u4FA1\u57FA\u6E96\u306B\u3088\u308B\u4E00\u8CAB\u3057\u305FAI\u30B9\u30B3\u30A2\u30EA\u30F3\u30B0\u3092\u5B9F\u73FE",
            "bullets",
          ),
          bulletItem(
            "\u30EC\u30FC\u30C0\u30FC\u30C1\u30E3\u30FC\u30C8\u30FB1\u6B21\u901A\u904E\u5019\u88DC\u5224\u5B9A\u30FB\u5099\u8003\u6B04\u3092\u542B\u3080\u30EA\u30C3\u30C1\u306AExcel\u30EC\u30DD\u30FC\u30C8",
            "bullets",
          ),
          bulletItem(
            "\u30EF\u30F3\u30AF\u30EA\u30C3\u30AF\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\uFF08setup.bat\uFF09\u3067\u6280\u8853\u8005\u3067\u306A\u3044\u30E6\u30FC\u30B6\u30FC\u3078\u306E\u5C55\u958B\u3092\u5BB9\u6613\u306B",
            "bullets",
          ),
          bulletItem(
            "PII\u30DE\u30B9\u30AD\u30F3\u30B0\u306B\u3088\u308B\u30D7\u30E9\u30A4\u30D0\u30B7\u30FC\u4FDD\u8B77",
            "bullets",
          ),

          new Paragraph({ children: [new PageBreak()] }),

          // === 2. TECH STACK ===
          heading(HeadingLevel.HEADING_1, "2. \u6280\u8853\u69CB\u6210"),
          heading(
            HeadingLevel.HEADING_2,
            "2.1 \u6280\u8853\u30B9\u30BF\u30C3\u30AF\u4E00\u89A7",
          ),
          makeTable(
            [
              "\u30AB\u30C6\u30B4\u30EA",
              "\u6280\u8853\u540D",
              "\u30D0\u30FC\u30B8\u30E7\u30F3",
              "\u7528\u9014",
            ],
            [
              [
                "\u8A00\u8A9E",
                "Python",
                "3.10+",
                "\u30A2\u30D7\u30EA\u30B1\u30FC\u30B7\u30E7\u30F3\u5168\u4F53",
              ],
              [
                "\u30D6\u30E9\u30A6\u30B6\u81EA\u52D5\u5316",
                "Playwright",
                "1.40+",
                "HRMOS\u30ED\u30B0\u30A4\u30F3\u30FB\u30DA\u30FC\u30B8\u5DE1\u56DE\u30FB\u66F8\u985EDL",
              ],
              [
                "PDF\u89E3\u6790",
                "pdfplumber",
                "0.10+",
                "PDF\u304B\u3089\u306E\u30C6\u30AD\u30B9\u30C8\u62BD\u51FA",
              ],
              [
                "Word\u89E3\u6790",
                "python-docx",
                "1.0+",
                "DOCX\u304B\u3089\u306E\u30C6\u30AD\u30B9\u30C8\u62BD\u51FA",
              ],
              [
                "Excel\u64CD\u4F5C",
                "openpyxl",
                "3.1+",
                "XLSX\u89E3\u6790\u30FB\u30EC\u30DD\u30FC\u30C8\u751F\u6210",
              ],
              [
                "\u8A2D\u5B9A\u7BA1\u7406",
                "PyYAML",
                "6.0+",
                "YAML\u8A2D\u5B9A\u30D5\u30A1\u30A4\u30EB\u306E\u8AAD\u307F\u8FBC\u307F",
              ],
              [
                "\u30E1\u30FC\u30EB\u901A\u77E5",
                "Resend",
                "2.0+",
                "\u8A55\u4FA1\u7D50\u679C\u306E\u30E1\u30FC\u30EB\u9001\u4FE1",
              ],
              [
                "AI\u8A55\u4FA1",
                "Claude CLI / Gemini CLI",
                "\u2014",
                "\u66F8\u985E\u30C6\u30AD\u30B9\u30C8\u306E\u8A55\u4FA1\u30FB\u30B9\u30B3\u30A2\u30EA\u30F3\u30B0",
              ],
              [
                "\u30C7\u30FC\u30BF\u30D9\u30FC\u30B9",
                "SQLite",
                "\u6A19\u6E96\u30E9\u30A4\u30D6\u30E9\u30EA",
                "\u5FDC\u52DF\u8005\u30FB\u8A55\u4FA1\u7D50\u679C\u306E\u6C38\u7D9A\u5316",
              ],
              [
                "\u30D6\u30E9\u30A6\u30B6",
                "Chromium",
                "Playwright\u81EA\u52D5\u7BA1\u7406",
                "HRMOS Web\u30A2\u30AF\u30BB\u30B9",
              ],
            ],
            [1400, 2200, 1800, 3626],
          ),

          heading(HeadingLevel.HEADING_2, "2.2 \u9078\u5B9A\u7406\u7531"),
          body(
            "Playwright: HRMOS\u306E2\u6BB5\u968E\u30ED\u30B0\u30A4\u30F3\u3084SPA\u7684\u306A\u753B\u9762\u9077\u79FB\u306B\u5BFE\u5FDC\u3059\u308B\u305F\u3081\u3001\u30D8\u30C3\u30C9\u30EC\u30B9\u30D6\u30E9\u30A6\u30B6\u81EA\u52D5\u5316\u304C\u5FC5\u8981\u3002Selenium\u6BD4\u3067\u30E2\u30C0\u30F3\u306AAPI\u8A2D\u8A08\u3068async\u5BFE\u5FDC\u304C\u5229\u70B9\u3002",
          ),
          body(
            "Claude CLI / Gemini CLI: API\u30AD\u30FC\u306E\u7BA1\u7406\u304C\u4E0D\u8981\u3067\u3001\u30ED\u30FC\u30AB\u30EBCLI\u8A8D\u8A3C\u306E\u307F\u3067\u52D5\u4F5C\u3002subprocess\u7D4C\u7531\u306E\u547C\u3073\u51FA\u3057\u3067\u30B7\u30F3\u30D7\u30EB\u306A\u7D71\u5408\u3092\u5B9F\u73FE\u3002config.yaml\u3067\u5207\u66FF\u53EF\u80FD\u306A\u8A2D\u8A08\u3002",
          ),
          body(
            "SQLite: \u5916\u90E8\u30B5\u30FC\u30D0\u30FC\u4E0D\u8981\u3067\u30D5\u30A1\u30A4\u30EB\u30D9\u30FC\u30B9\u306E\u6C38\u7D9A\u5316\u304C\u53EF\u80FD\u3002\u5C0F\u301C\u4E2D\u898F\u6A21\u306E\u5FDC\u52DF\u8005\u30C7\u30FC\u30BF\u306B\u6700\u9069\u3002",
          ),
          body(
            "openpyxl: \u30EC\u30FC\u30C0\u30FC\u30C1\u30E3\u30FC\u30C8\u30FB\u6761\u4EF6\u4ED8\u304D\u66F8\u5F0F\u30FB\u8272\u4ED8\u304D\u30BB\u30EB\u306A\u3069\u30EA\u30C3\u30C1\u306AExcel\u51FA\u529B\u306B\u5BFE\u5FDC\u3002",
          ),

          new Paragraph({ children: [new PageBreak()] }),

          // === 3. ARCHITECTURE ===
          heading(
            HeadingLevel.HEADING_1,
            "3. \u30A2\u30FC\u30AD\u30C6\u30AF\u30C1\u30E3",
          ),
          heading(
            HeadingLevel.HEADING_2,
            "3.1 \u30A2\u30FC\u30AD\u30C6\u30AF\u30C1\u30E3\u6982\u8981",
          ),
          body(
            "\u672C\u30C4\u30FC\u30EB\u306F5\u5C64\u306E\u30EC\u30A4\u30E4\u30FC\u30C9\u30A2\u30FC\u30AD\u30C6\u30AF\u30C1\u30E3\u3067\u69CB\u6210\u3055\u308C\u3066\u3044\u308B\u3002CLI\u304B\u3089\u30AA\u30FC\u30B1\u30B9\u30C8\u30EC\u30FC\u30BF\u30FC\uFF08main.py\uFF09\u3092\u7D4C\u7531\u3057\u3066\u5404\u5C64\u3092\u9806\u6B21\u547C\u3073\u51FA\u3059\u8A2D\u8A08\u306B\u3088\u308A\u3001\u95A2\u5FC3\u306E\u5206\u96E2\u3068\u4FDD\u5B88\u6027\u3092\u78BA\u4FDD\u3057\u3066\u3044\u308B\u3002",
          ),
          ...imageBlock(
            "diagram1.png",
            "\u56F33-1: \u30B7\u30B9\u30C6\u30E0\u69CB\u6210\u56F3",
            450,
            500,
          ),

          heading(HeadingLevel.HEADING_2, "3.2 \u51E6\u7406\u30D5\u30ED\u30FC"),
          body(
            "scan\u30B3\u30DE\u30F3\u30C9\u5B9F\u884C\u6642\u306E\u51E6\u7406\u30D5\u30ED\u30FC\u3092\u4EE5\u4E0B\u306B\u793A\u3059\u3002",
          ),
          ...imageBlock(
            "diagram2.png",
            "\u56F33-2: scan\u30B3\u30DE\u30F3\u30C9\u51E6\u7406\u30D5\u30ED\u30FC",
            500,
            200,
          ),

          heading(
            HeadingLevel.HEADING_2,
            "3.3 \u8A2D\u8A08\u65B9\u91DD\u30FB\u5DE5\u592B",
          ),
          heading(
            HeadingLevel.HEADING_3,
            "LLM CLI subprocess\u547C\u3073\u51FA\u3057",
          ),
          body(
            "API\u30AD\u30FC\u306E\u7BA1\u7406\u3092\u4E0D\u8981\u306B\u3059\u308B\u305F\u3081\u3001Claude CLI\uFF08claude -p\uFF09\u3084Gemini CLI\u3092subprocess.run\u3067\u547C\u3073\u51FA\u3059\u8A2D\u8A08\u3092\u63A1\u7528\u3002stdin\u306B\u30D7\u30ED\u30F3\u30D7\u30C8\u3092\u9001\u308A\u3001stdout\u304B\u3089JSON\u5FDC\u7B54\u3092\u53D7\u3051\u53D6\u308B\u3002\u74B0\u5883\u5909\u6570 CLAUDECODE \u3092\u9664\u53BB\u3057\u3066\u30CD\u30B9\u30C8\u30BB\u30C3\u30B7\u30E7\u30F3\u3092\u9632\u6B62\u3059\u308B\u5DE5\u592B\u3082\u65BD\u3057\u3066\u3044\u308B\u3002",
          ),
          heading(HeadingLevel.HEADING_3, "PII\u30DE\u30B9\u30AD\u30F3\u30B0"),
          body(
            "LLM\u306B\u500B\u4EBA\u60C5\u5831\u3092\u9001\u4FE1\u3057\u306A\u3044\u3088\u3046\u3001\u8A55\u4FA1\u524D\u306B\u6C0F\u540D\u30FB\u96FB\u8A71\u756A\u53F7\u30FB\u4F4F\u6240\u3092\u30DE\u30B9\u30AF\u3057\u3001\u5FDC\u7B54\u5F8C\u306B\u30A2\u30F3\u30DE\u30B9\u30AF\u3059\u308B\u53EF\u9006\u30DE\u30B9\u30AD\u30F3\u30B0\u3092\u5B9F\u88C5\u3002\u6C0F\u540D\u306E\u5168\u89D2/\u534A\u89D2/\u30B9\u30DA\u30FC\u30B9\u306A\u3057\u306A\u3069\u8907\u6570\u306E\u8868\u8A18\u30D1\u30BF\u30FC\u30F3\u306B\u5BFE\u5FDC\u3002",
          ),
          heading(HeadingLevel.HEADING_3, "Repository\u30D1\u30BF\u30FC\u30F3"),
          body(
            "\u30C7\u30FC\u30BF\u30D9\u30FC\u30B9\u30A2\u30AF\u30BB\u30B9\u3092Repository\u5C64\u306B\u96C6\u7D04\u3057\u3001\u30D3\u30B8\u30CD\u30B9\u30ED\u30B8\u30C3\u30AF\u304B\u3089SQL\u64CD\u4F5C\u3092\u5206\u96E2\u3002\u30C6\u30FC\u30D6\u30EB\u69CB\u9020\u306E\u5909\u66F4\u304C\u30A2\u30D7\u30EA\u30B1\u30FC\u30B7\u30E7\u30F3\u5C64\u306B\u5F71\u97FF\u3057\u306B\u304F\u3044\u8A2D\u8A08\u3002",
          ),
          heading(
            HeadingLevel.HEADING_3,
            "CSS\u30BB\u30EC\u30AF\u30BF\u96C6\u7D04",
          ),
          body(
            "HRMOS\u306EUI\u5909\u66F4\u306B\u5099\u3048\u3001\u5168\u30DA\u30FC\u30B8\u8981\u7D20\u306ECSS\u30BB\u30EC\u30AF\u30BF\u3092selectors.py\u306B\u96C6\u7D04\u3002UI\u5909\u66F4\u6642\u306E\u4FEE\u6B63\u7B87\u6240\u30921\u30D5\u30A1\u30A4\u30EB\u306B\u9650\u5B9A\u3002",
          ),

          heading(
            HeadingLevel.HEADING_2,
            "3.4 \u30C7\u30FC\u30BF\u30D9\u30FC\u30B9\u8A2D\u8A08",
          ),
          body("SQLite\u30674\u30C6\u30FC\u30D6\u30EB\u3092\u69CB\u6210\u3002"),
          makeTable(
            [
              "\u30C6\u30FC\u30D6\u30EB",
              "\u5F79\u5272",
              "\u4E3B\u306A\u30AB\u30E9\u30E0",
            ],
            [
              [
                "applicants",
                "\u5FDC\u52DF\u8005\u30DE\u30B9\u30BF",
                "id, name, page_url, status (pending/scanned/error)",
              ],
              [
                "documents",
                "\u6DFB\u4ED8\u66F8\u985E",
                "applicant_id, filename, file_type, text_length",
              ],
              [
                "evaluations",
                "AI\u8A55\u4FA1\u7D50\u679C",
                "applicant_id, criterion_name, score, comment",
              ],
              [
                "scan_runs",
                "\u5B9F\u884C\u5C65\u6B74",
                "id, started_at, completed_at, status",
              ],
            ],
            [1800, 2000, 5226],
          ),
          body(
            "--all\u30AA\u30D7\u30B7\u30E7\u30F3\u4F7F\u7528\u6642\u306F\u5168applicants\u306Estatus\u3092pending\u306B\u30EA\u30BB\u30C3\u30C8\u3057\u3001\u518D\u8A55\u4FA1\u3092\u5B9F\u884C\u3059\u308B\u3002",
          ),

          new Paragraph({ children: [new PageBreak()] }),

          // === 8. IMPROVEMENT HISTORY ===
          heading(HeadingLevel.HEADING_1, "4. \u6539\u5584\u5C65\u6B74"),
          heading(
            HeadingLevel.HEADING_2,
            "4.1 \u6539\u5584\u5C65\u6B74\u30C6\u30FC\u30D6\u30EB",
          ),
          makeTable(
            [
              "\u65E5\u4ED8",
              "\u5BFE\u8C61",
              "\u5909\u66F4\u5185\u5BB9",
              "\u7406\u7531",
            ],
            [
              [
                "2026-02-17",
                "\u5168\u4F53",
                "\u521D\u56DE\u30B3\u30DF\u30C3\u30C8",
                "\u30D7\u30ED\u30B8\u30A7\u30AF\u30C8\u958B\u59CB",
              ],
              [
                "2026-02-20",
                "browser/",
                "Playwright locator API\u79FB\u884C\u30FB2\u6BB5\u968E\u30ED\u30B0\u30A4\u30F3\u5BFE\u5FDC",
                "HRMOS\u8A8D\u8A3C\u4ED5\u69D8\u3078\u306E\u5BFE\u5FDC",
              ],
              [
                "2026-02-22",
                "reporter/",
                "Resend\u30E1\u30FC\u30EB\u901A\u77E5\u30FB\u30BF\u30B9\u30AF\u30B9\u30B1\u30B8\u30E5\u30FC\u30E9\u5BFE\u5FDC",
                "\u904B\u7528\u81EA\u52D5\u5316",
              ],
              [
                "2026-02-24",
                "evaluator/",
                "\u30AD\u30FC\u30EF\u30FC\u30C9\u30B9\u30AD\u30E3\u30F3\u304B\u3089Claude AI\u81EA\u52D5\u8A55\u4FA1\u306B\u5168\u9762\u7F6E\u63DB",
                "\u8A55\u4FA1\u7CBE\u5EA6\u306E\u5927\u5E45\u5411\u4E0A",
              ],
              [
                "2026-02-25",
                "evaluator/",
                "Gemini AI\u8A55\u4FA1\u3078\u306E\u5BFE\u5FDC\u3068LLM\u30AF\u30E9\u30A4\u30A2\u30F3\u30C8\u306E\u62BD\u8C61\u5316",
                "\u30D7\u30ED\u30D0\u30A4\u30C0\u30FC\u5207\u66FF\u306E\u67D4\u8EDF\u6027\u78BA\u4FDD",
              ],
              [
                "2026-03-01",
                "evaluator/",
                "Claude CLI\u30CD\u30B9\u30C8\u30BB\u30C3\u30B7\u30E7\u30F3\u691C\u51FA\u306B\u3088\u308B\u30BF\u30A4\u30E0\u30A2\u30A6\u30C8\u4FEE\u6B63",
                "CLAUDECODE\u74B0\u5883\u5909\u6570\u306E\u9664\u53BB",
              ],
              [
                "2026-03-03",
                "config",
                "LLM CLI\u30BF\u30A4\u30E0\u30A2\u30A6\u30C8\u3092120\u79D2\u2192300\u79D2\u306B\u5909\u66F4",
                "\u9577\u6587\u66F8\u985E\u3067\u306E\u8A55\u4FA1\u5931\u6557\u9632\u6B62",
              ],
              [
                "2026-03-05",
                "main.py",
                "\u5B9F\u65BD\u6E08\u307F\u5224\u5B9A\u306E\u4E0D\u5099\u4FEE\u6B63\u30FB\u30A8\u30E9\u30FC\u30EA\u30C8\u30E9\u30A4\u6A5F\u80FD\u8FFD\u52A0",
                "\u51E6\u7406\u306E\u4FE1\u983C\u6027\u5411\u4E0A",
              ],
              [
                "2026-03-06",
                "evaluator/",
                "LLM\u9001\u4FE1\u524D\u306EPII\u30DE\u30B9\u30AD\u30F3\u30B0\u6A5F\u80FD\u8FFD\u52A0",
                "\u30D7\u30E9\u30A4\u30D0\u30B7\u30FC\u4FDD\u8B77",
              ],
              [
                "2026-03-07",
                "reporter/",
                "\u30EC\u30FC\u30C0\u30FC\u30C1\u30E3\u30FC\u30C8\u30FB1\u6B21\u901A\u904E\u5019\u88DC\u30FB\u5099\u8003\u6B04\u306E\u8FFD\u52A0",
                "\u30EC\u30DD\u30FC\u30C8\u306E\u60C5\u5831\u91CF\u30FB\u8996\u8A8D\u6027\u5411\u4E0A",
              ],
              [
                "2026-03-07",
                "setup.bat\u7B49",
                "\u30EF\u30F3\u30AF\u30EA\u30C3\u30AF\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\u30FB\u30D0\u30C3\u30C1\u30D1\u30B9\u52D5\u7684\u5316",
                "\u5225PC\u5C55\u958B\u306E\u5BB9\u6613\u5316",
              ],
            ],
            [1200, 1200, 4000, 2626],
          ),

          heading(HeadingLevel.HEADING_2, "4.2 \u50BE\u5411\u5206\u6790"),
          body(
            "\u6539\u5584\u6D3B\u52D5\u306F\u5927\u304D\u304F3\u3064\u306E\u30D5\u30A7\u30FC\u30BA\u306B\u5206\u985E\u3067\u304D\u308B\u3002",
          ),
          body(
            "1. \u57FA\u76E4\u69CB\u7BC9\u671F\uFF082/17\u301C2/22\uFF09: \u30D6\u30E9\u30A6\u30B6\u81EA\u52D5\u5316\u30FB\u30E1\u30FC\u30EB\u901A\u77E5\u30FB\u30B9\u30B1\u30B8\u30E5\u30FC\u30E9\u306A\u3069\u30A4\u30F3\u30D5\u30E9\u9762\u306E\u6574\u5099",
            { bold: true },
          ),
          body(
            "2. AI\u8A55\u4FA1\u5F37\u5316\u671F\uFF082/24\u301C3/6\uFF09: \u30AD\u30FC\u30EF\u30FC\u30C9\u30DE\u30C3\u30C1\u304B\u3089LLM\u8A55\u4FA1\u3078\u306E\u79FB\u884C\u3001\u30DE\u30EB\u30C1\u30D7\u30ED\u30D0\u30A4\u30C0\u30FC\u5BFE\u5FDC\u3001PII\u4FDD\u8B77\u306A\u3069\u30B3\u30A2\u6A5F\u80FD\u306E\u9AD8\u5EA6\u5316",
            { bold: true },
          ),
          body(
            "3. UX\u6539\u5584\u671F\uFF083/7\uFF09: \u30EC\u30DD\u30FC\u30C8\u306E\u53EF\u8996\u5316\u5F37\u5316\uFF08\u30EC\u30FC\u30C0\u30FC\u30C1\u30E3\u30FC\u30C8\u7B49\uFF09\u3068\u975E\u6280\u8853\u8005\u5411\u3051\u30BB\u30C3\u30C8\u30A2\u30C3\u30D7\u306E\u7C21\u7D20\u5316",
            { bold: true },
          ),

          new Paragraph({ children: [new PageBreak()] }),

          // === 11. FUTURE OUTLOOK ===
          heading(HeadingLevel.HEADING_1, "5. \u4ECA\u5F8C\u306E\u5C55\u671B"),
          heading(
            HeadingLevel.HEADING_2,
            "5.1 \u77ED\u671F\u6539\u5584\uFF081-3\u30F6\u6708\uFF09",
          ),
          makeTable(
            ["\u9805\u76EE", "\u5185\u5BB9", "\u512A\u5148\u5EA6"],
            [
              [
                "\u30C6\u30B9\u30C8\u30D5\u30EC\u30FC\u30E0\u30EF\u30FC\u30AF\u5C0E\u5165",
                "pytest\u7B49\u3092\u7528\u3044\u305F\u81EA\u52D5\u30C6\u30B9\u30C8\u306E\u6574\u5099\u3002\u73FE\u5728\u306Ftest_pii_masker.py\u306E\u307F",
                "\u9AD8",
              ],
              [
                ".doc\uFF08\u65E7\u5F62\u5F0F\uFF09\u5BFE\u5FDC",
                "python-docx\u3067\u306F\u8AAD\u3081\u306A\u3044.doc\u30D5\u30A1\u30A4\u30EB\u3078\u306E\u5BFE\u5FDC",
                "\u4E2D",
              ],
              [
                "\u30D8\u30C3\u30C9\u30EC\u30B9\u30E2\u30FC\u30C9\u6700\u9069\u5316",
                "headless: true\u3067\u306E\u5B89\u5B9A\u52D5\u4F5C\u691C\u8A3C\u30FB\u6700\u9069\u5316",
                "\u4E2D",
              ],
              [
                "\u30A8\u30E9\u30FC\u30CF\u30F3\u30C9\u30EA\u30F3\u30B0\u5F37\u5316",
                "\u30CD\u30C3\u30C8\u30EF\u30FC\u30AF\u65AD\u30FBHRMOS\u969C\u5BB3\u6642\u306E\u30B0\u30EC\u30FC\u30B9\u30D5\u30EB\u30EA\u30AB\u30D0\u30EA",
                "\u4E2D",
              ],
            ],
            [2400, 5226, 1400],
          ),

          heading(
            HeadingLevel.HEADING_2,
            "5.2 \u4E2D\u9577\u671F\u8A08\u753B\uFF083-12\u30F6\u6708\uFF09",
          ),
          makeTable(
            ["\u9805\u76EE", "\u5185\u5BB9", "\u512A\u5148\u5EA6"],
            [
              [
                "Web UI / \u30C0\u30C3\u30B7\u30E5\u30DC\u30FC\u30C9",
                "\u8A55\u4FA1\u7D50\u679C\u306E\u53EF\u8996\u5316\u30FB\u30D5\u30A3\u30EB\u30BF\u30EA\u30F3\u30B0\u3092\u30D6\u30E9\u30A6\u30B6UI\u3067\u63D0\u4F9B",
                "\u4E2D",
              ],
              [
                "\u8907\u6570\u6C42\u4EBA\u5BFE\u5FDC",
                "\u6C42\u4EBA\u3054\u3068\u306B\u7570\u306A\u308B\u8A55\u4FA1\u57FA\u6E96\u3092\u9069\u7528\u3067\u304D\u308B\u4ED5\u7D44\u307F",
                "\u4E2D",
              ],
              [
                "API\u5316",
                "\u4ED6\u30B7\u30B9\u30C6\u30E0\u3068\u306E\u9023\u643A\u306E\u305F\u3081\u306EREST API\u63D0\u4F9B",
                "\u4F4E",
              ],
              [
                "\u8A55\u4FA1\u7CBE\u5EA6\u306E\u30D5\u30A3\u30FC\u30C9\u30D0\u30C3\u30AF\u30EB\u30FC\u30D7",
                "\u5B9F\u969B\u306E\u63A1\u7528\u7D50\u679C\u3068AI\u8A55\u4FA1\u306E\u76F8\u95A2\u5206\u6790\u30FB\u57FA\u6E96\u6539\u5584",
                "\u4F4E",
              ],
            ],
            [2400, 5226, 1400],
          ),

          heading(HeadingLevel.HEADING_2, "5.3 \u63A8\u5968\u4E8B\u9805"),
          bulletItem(
            "\u30C6\u30B9\u30C8\u6574\u5099\u3092\u512A\u5148\u3057\u3001\u56DE\u5E30\u30C6\u30B9\u30C8\u306A\u3057\u3067\u306E\u6539\u4FEE\u30EA\u30B9\u30AF\u3092\u8EFD\u6E1B\u3059\u308B",
            "bullets",
          ),
          bulletItem(
            "\u8A55\u4FA1\u57FA\u6E96\u306E\u5B9A\u671F\u898B\u76F4\u3057\u30D7\u30ED\u30BB\u30B9\u3092\u78BA\u7ACB\u3059\u308B\uFF083\u30F6\u6708\u3054\u3068\u306E\u632F\u308A\u8FD4\u308A\u3092\u63A8\u5968\uFF09",
            "bullets",
          ),
          bulletItem(
            "\u5229\u7528\u8005\u304B\u3089\u306E\u30D5\u30A3\u30FC\u30C9\u30D0\u30C3\u30AF\u53CE\u96C6\u306E\u4ED5\u7D44\u307F\u3092\u8A2D\u3051\u308B",
            "bullets",
          ),
        ],
      },
    ],
  });

  const buffer = await Packer.toBuffer(doc);
  const outPath = path.join(
    __dirname,
    "AGS_HRMOS_AUTO_EVAL_\u7DCF\u62EC\u5831\u544A\u66F8_20260307.docx",
  );
  fs.writeFileSync(outPath, buffer);
  console.log("Generated: " + outPath);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
