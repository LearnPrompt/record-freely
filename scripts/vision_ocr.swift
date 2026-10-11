import Foundation
import Vision
import ImageIO

// Persistent JSON-lines worker. Images and recognition stay on this Mac.
func rect(_ box: CGRect) -> [Double] {
    [Double(box.minX), Double(1 - box.maxY), Double(box.width), Double(box.height)]
}


// Accurate OCR sometimes assigns the same word box to several characters.
// A separate fast recognition supplies independently observed glyph geometry;
// its text and boxes stay paired. Never divide a line by string length.
func fastGeometry(_ path: String) throws -> [[String: Any]] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .fast
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = false
    request.minimumTextHeight = 0.002
    try VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:]).perform([request])
    var output: [[String: Any]] = []
    for observation in request.results ?? [] {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let string = candidate.string
        guard string.range(of: #"[.．/／\\]|https?"#, options: [.regularExpression, .caseInsensitive]) != nil else { continue }
        var characters: [[String: Any]] = []
        for index in string.indices {
            let end = string.index(after: index)
            if let box = try candidate.boundingBox(for: index..<end) {
                let first = string[..<index].unicodeScalars.count
                let last = first + string[index..<end].unicodeScalars.count
                characters.append(["start": first, "end": last, "box": rect(box.boundingBox)])
            }
        }
        output.append(["text": string, "confidence": candidate.confidence,
                       "box": rect(observation.boundingBox), "chars": characters,
                       "geometry_engine": "vision_fast"])
    }
    return output
}

func needsIndependentGeometry(_ observations: [[String: Any]]) -> Bool {
    for observation in observations {
        guard let chars = observation["chars"] as? [[String: Any]] else { continue }
        var boxes = Set<[Double]>()
        for character in chars {
            if let box = character["box"] as? [Double], !boxes.insert(box).inserted { return true }
        }
    }
    return false
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
            request.recognitionLanguages = ["en-US", "zh-Hans"]
            request.usesLanguageCorrection = false
            request.minimumTextHeight = 0.002
            let privacy = input["privacy"] as? Bool ?? false
            let barcodeRequest = VNDetectBarcodesRequest()
            try VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:]).perform(privacy ? [request, barcodeRequest] : [request])
            var observations: [[String: Any]] = []
            for observation in request.results ?? [] {
                guard let candidate = observation.topCandidates(1).first else { continue }
                let string = candidate.string
                var characters: [[String: Any]] = []
                // Offsets are Unicode scalar positions, matching Python's indexing.
                // Only possible URL lines need costly per-character geometry.
                let needsGeometry = privacy || string.contains(".") || string.contains("．") || string.lowercased().contains("http")
                for index in needsGeometry ? Array(string.indices) : [] {
                    let end = string.index(after: index)
                    if let box = try candidate.boundingBox(for: index..<end) {
                        let startOffset = string[..<index].unicodeScalars.count
                        let endOffset = startOffset + string[index..<end].unicodeScalars.count
                        characters.append(["start": startOffset, "end": endOffset, "box": rect(box.boundingBox)])
                    }
                }
                observations.append(["text": string, "confidence": candidate.confidence,
                                     "box": rect(observation.boundingBox), "chars": characters])
            }
            if needsIndependentGeometry(observations), let extra = try? fastGeometry(path) {
                observations.append(contentsOf: extra)
            }
            let codes: [[String: Any]] = privacy ? (barcodeRequest.results ?? []).filter { $0.symbology == .qr }.map {
                ["kind": "qr_code", "text": "", "box": rect($0.boundingBox), "confidence": 1.0]
            } : []
            let output = try JSONSerialization.data(withJSONObject: ["observations": observations, "codes": codes], options: [.sortedKeys])
            print(String(decoding: output, as: UTF8.self))
            fflush(stdout)
        } catch {
            let output = try! JSONSerialization.data(withJSONObject: ["error": error.localizedDescription])
            print(String(decoding: output, as: UTF8.self))
            fflush(stdout)
        }
    }
}
