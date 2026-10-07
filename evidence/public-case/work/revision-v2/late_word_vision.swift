import Foundation
import Vision
import ImageIO

// Persistent JSON-lines worker. Images and recognition stay on this Mac.
func rect(_ box: CGRect) -> [Double] {
    [Double(box.minX), Double(1 - box.maxY), Double(box.width), Double(box.height)]
}

while let line = readLine() {
    autoreleasepool {
        do {
            guard let data = line.data(using: .utf8),
                  let input = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let path = input["path"] as? String else {
                throw NSError(domain: "OCR", code: 1, userInfo: [NSLocalizedDescriptionKey: "Invalid input"])
            }
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["zh-Hans", "en-US"]
            request.usesLanguageCorrection = false
            request.minimumTextHeight = 0.002
            try VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:]).perform([request])
            var observations: [[String: Any]] = []
            for observation in request.results ?? [] {
                guard let candidate = observation.topCandidates(1).first else { continue }
                let string = candidate.string
                var characters: [[String: Any]] = []
                // Offsets are Unicode scalar positions, matching Python's indexing.
                // Only possible URL lines need costly per-character geometry.
                let needsGeometry = false
                for index in needsGeometry ? Array(string.indices) : [] {
                    let end = string.index(after: index)
                    if let box = try candidate.boundingBox(for: index..<end) {
                        let startOffset = string[..<index].unicodeScalars.count
                        let endOffset = startOffset + string[index..<end].unicodeScalars.count
                        characters.append(["start": startOffset, "end": endOffset, "box": rect(box.boundingBox)])
                    }
                }
                var matches: [[String: Any]] = []
                let patterns = ["path": "/[Uu]sers/[Cc]arl/", "extension": "[.．]html", "word_b": "[Bb]站", "word_x": "小红书", "word_c": "中国"]
                for (key, pattern) in patterns {
                    if let regex = try? NSRegularExpression(pattern: pattern) {
                        for match in regex.matches(in: string, range: NSRange(string.startIndex..., in: string)) {
                            if let range = Range(match.range, in: string), let box = try? candidate.boundingBox(for: range) {
                                matches.append(["target": key, "start": string[..<range.lowerBound].unicodeScalars.count, "end": string[..<range.upperBound].unicodeScalars.count, "box": rect(box.boundingBox)])
                            }
                        }
                    }
                }
                observations.append(["matches": matches, "text": string, "confidence": candidate.confidence,
                                     "box": rect(observation.boundingBox), "chars": characters])
            }
            let output = try JSONSerialization.data(withJSONObject: ["observations": observations], options: [.sortedKeys])
            print(String(decoding: output, as: UTF8.self))
            fflush(stdout)
        } catch {
            let output = try! JSONSerialization.data(withJSONObject: ["error": error.localizedDescription])
            print(String(decoding: output, as: UTF8.self))
            fflush(stdout)
        }
    }
}
