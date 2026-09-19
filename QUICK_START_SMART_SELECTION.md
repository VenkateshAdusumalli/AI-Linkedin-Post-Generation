# Quick Start Guide - Smart Video Selection

## What's New?

The AI LinkedIn Agent now:
- **Evaluates video content quality** before processing
- **Respects channel priorities** properly (P1 first, P2 only if P1 has no suitable videos)
- **Uses video frames** for visual analysis when transcripts are insufficient
- **Only marks videos as processed** after complete pipeline success
- **Skips poor-quality videos** without marking them processed for later re-evaluation

## Installation

### 1. Install New Dependencies

```bash
pip install -r requirements.txt
```

New packages added:
- `yt-dlp` - For downloading videos to extract frames
- `opencv-python` - For frame extraction

### 2. Verify Environment

Ensure `.env` has all required keys:

```env
YOUTUBE_API_KEY=your_youtube_key
GEMINI_API_KEY=your_gemini_key
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_API_TOKEN=your_api_token
LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token
LINKEDIN_MEMBER_ID=your_member_id

# Priority 1 Channel
CHANNEL_1_NAME=Vaibhav Sisinty
CHANNEL_1_ID=UC...

# Priority 2 Channel
CHANNEL_2_NAME=ThinkSchool
CHANNEL_2_ID=UC...
```

## Running the System

### Basic Run

```bash
python main.py
```

This will:
1. Check Priority 1 channel for new unprocessed videos
2. Evaluate each video's content quality (up to 5 candidates)
3. Select the first GOOD quality video
4. Process it through the full pipeline (transcript → post → image → publish)
5. Only mark as PROCESSED after complete success

### Console Output Example

```
============================================================
YouTube Multi-Channel Priority Check
Smart Video Selection + Content Quality Evaluation
============================================================

Checking Priority 1: Vaibhav Sisinty

  Found 3 new unprocessed video(s).

  Evaluating: He Built an AI App That Files Pothole...
    Checking transcript quality...
    Transcript quality: LOW
    Analyzing selected video frames...
    Frames analyzed.
    Analyzing content with Gemini...
    Content quality: POOR
    Reason: Insufficient information...

  ✗ Skipping due to poor content quality.

  Evaluating: Another Video...
    Checking transcript quality...
    Transcript quality: HIGH
    Analyzing content with Gemini...
    Content quality: GOOD

  ✓ Selected video: Another Video...

============================================================
PROCESSING VIDEO
Title: Another Video...
Video ID: dQw4w9WgXcQ

Getting transcript...
Transcript retrieved successfully.

Generating LinkedIn post...
...
```

## Testing

Run unit tests before production:

```bash
python test_smart_selection.py
```

All tests should show green checkmarks:
```
✓ Test 1 passed: Low quality transcript detection
✓ Test 2 passed: High quality transcript detection
...
All tests passed! ✓
```

## How It Works

### 1. Smart Video Selection

For each channel (in priority order):
- Get up to 5 newest unprocessed videos
- Evaluate each video's content quality
- Select the first video with GOOD quality
- Stop looking at older videos once a suitable one is found

### 2. Content Quality Evaluation

For each candidate video:
1. **Extract transcript** from YouTube
2. **Analyze transcript quality** (length, completeness)
3. **If transcript is poor**, extract representative video frames
4. **Send to Gemini** for comprehensive analysis:
   - Title + Description + Transcript + Visual info
   - Returns: GOOD or POOR classification
   - Includes confidence level and reasoning
5. **Decision:**
   - GOOD → Process the video
   - POOR → Skip to next candidate

### 3. Frame Extraction (When Needed)

If transcript quality is insufficient:
- Download video (yt-dlp)
- Extract frames at: 10%, 25%, 40%, 55%, 70%, 85%
- Analyze frames with Gemini
- Automatically delete temporary files

### 4. Processing Pipeline (Only for GOOD Videos)

Once a suitable video is selected:
1. Extract transcript
2. Generate LinkedIn post (Gemini)
3. Generate image (Cloudflare FLUX)
4. Publish to LinkedIn
5. **Mark as PROCESSED** ← Only happens on complete success

## Failure Modes

### If Transcript Extraction Fails
- Video skipped
- NOT marked as processed
- Will be reconsidered next run

### If Content Quality is POOR
- Video skipped
- NOT marked as processed
- Will be reconsidered next run

### If LinkedIn Publishing Fails
- Video NOT marked as processed
- Can retry next run

### If Image Generation Fails
- Video NOT marked as processed
- Can retry next run

**Summary**: Only successful videos get marked PROCESSED.

## Customization

### Adjust Number of Candidates Evaluated

Edit `main.py`, in the `main()` function:

```python
# Default: check up to 5 unprocessed videos per channel
result = find_suitable_video_in_channel(channel, max_candidates=5)

# Change to 10 for more thorough evaluation:
result = find_suitable_video_in_channel(channel, max_candidates=10)
```

### Adjust Transcript Quality Thresholds

Edit `agents/content_analyzer.py`:

```python
def analyze_transcript_quality(...):
    MIN_GOOD_LENGTH = 500    # Change for different threshold
    MIN_ACCEPTABLE_LENGTH = 200
```

### Skip Frame Analysis

Frame extraction is optional. If you want to skip it:

Edit `agents/content_analyzer.py`, in `evaluate_video_quality()`:

```python
# Comment out or remove this section:
if transcript_quality in ["LOW", "MEDIUM"]:
    print("    Analyzing selected video frames...")
    visual_info = get_visual_analysis(video_id, transcript)
```

## Database Tracking

The system uses SQLite to prevent reprocessing videos:

- Located: `database/videos.db`
- Table: `videos`
- Fields: channel_id, video_id, video_title, published_at, processed_at
- Only videos with complete pipeline success are recorded

To check processed videos:

```bash
sqlite3 database/videos.db "SELECT video_id, video_title, processed_at FROM videos;"
```

To manually mark a video (for testing):

```bash
sqlite3 database/videos.db "INSERT INTO videos (channel_id, video_id, video_title, published_at, processed_at) VALUES ('CHANNEL_ID', 'VIDEO_ID', 'Title', '2024-01-01', datetime('now'));"
```

## Troubleshooting

### "No new videos found on any channel"
- Check if all videos are marked as processed
- Use: `sqlite3 database/videos.db "SELECT COUNT(*) FROM videos;"`
- If needed, delete the database to start fresh: `rm database/videos.db`

### "Transcript unavailable for video"
- Some videos have disabled transcripts
- System will skip them and try next video

### "Gemini returned no content"
- API key issue or quota exceeded
- Check: `echo $GEMINI_API_KEY` (should not be empty)
- Check Gemini API usage on Google AI console

### Frames not being extracted
- OpenCV or yt-dlp installation issue
- Try: `pip install --upgrade opencv-python yt-dlp`
- Or disable frame extraction (see Customization section)

### LinkedIn publishing fails
- Check access token validity
- Verify member ID is correct
- Check LinkedIn rate limits

## Architecture Overview

```
main.py
  ├─ youtube_client.get_candidate_videos() → Get 5 videos
  ├─ For each candidate:
  │  ├─ transcript.extract_transcript()
  │  ├─ content_analyzer.analyze_transcript_quality()
  │  ├─ frame_extractor.get_visual_analysis() [optional]
  │  └─ content_analyzer.analyze_video_content() [Gemini]
  │
  └─ If GOOD:
     ├─ linkedin_agent.generate_linkedin_post()
     ├─ image_agent.generate_linkedin_image()
     ├─ linkedin_client.publish_linkedin_post()
     └─ database.save_processed_video() [ONLY HERE]
```

## Performance Notes

- Typical evaluation time per video: 15-30 seconds (includes Gemini API calls)
- Frame extraction adds 30-60 seconds (downloads video, extracts frames, analyzes)
- Full pipeline per selected video: 2-3 minutes (includes image generation and LinkedIn publishing)
- YouTube API quota: ~100 calls per day (get 5 videos = 1 call per channel)

## Support

For detailed technical documentation, see:
- [SMART_SELECTION_IMPLEMENTATION.md](SMART_SELECTION_IMPLEMENTATION.md) - Architecture details
- [README.md](README.md) - Original project overview
- [test_smart_selection.py](test_smart_selection.py) - Test cases and examples
