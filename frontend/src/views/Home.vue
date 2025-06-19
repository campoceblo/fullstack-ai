<template>
  <div>
    <h1>AI Video Generator</h1>
    <form @submit.prevent="submitForm" enctype="multipart/form-data">
      <div>
        <label>Text Input:</label>
        <textarea v-model="textContent" placeholder="Enter text for audio generation" rows="5"></textarea>
      </div>
      
      <div>
        <label>Or Upload Audio:</label>
        <input type="file" @change="onAudioChange" accept="audio/*">
      </div>
      
      <div>
        <label>Upload Reference Video (Optional):</label>
        <input type="file" @change="onVideoChange" accept="video/*">
      </div>
      
      <button type="submit" :disabled="isSubmitting">Generate Video</button>
    </form>
    <p v-if="isSubmitting">Submitting your request...</p>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  data() {
    return {
      textContent: '',
      audioFile: null,
      videoFile: null,
      isSubmitting: false
    }
  },
  methods: {
    onAudioChange(e) {
      this.audioFile = e.target.files[0]
      if (this.audioFile) this.textContent = ''
    },
    onVideoChange(e) {
      this.videoFile = e.target.files[0]
    },
    async submitForm() {
      if (!this.textContent && !this.audioFile) {
        alert('Please provide either text or an audio file')
        return
      }
      
      this.isSubmitting = true
      
      const formData = new FormData()
      if (this.textContent) formData.append('text_content', this.textContent)
      if (this.audioFile) formData.append('audio_file', this.audioFile)
      if (this.videoFile) formData.append('video_file', this.videoFile)
      
      try {
        const response = await axios.post('/api/jobs/', formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        })
        
        this.$router.push({
          name: 'Result',
          params: { jobId: response.data.id }
        })
      } catch (error) {
        console.error('Error submitting job:', error)
        alert('Failed to submit job. Please try again.')
      } finally {
        this.isSubmitting = false
      }
    }
  }
}
</script>