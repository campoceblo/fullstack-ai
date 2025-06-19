<template>
  <div>
    <h1>Job Status</h1>
    <div v-if="job">
      <p>Job ID: {{ job.id }}</p>
      <p>Status: {{ job.status }}</p>
      
      <div v-if="job.status === 'COMPLETED'">
        <h2>Generated Video</h2>
        <video :src="getVideoUrl(job.path_minio_video_output)" controls autoplay></video>
      </div>
      
      <div v-else>
        <p>Processing... This may take several minutes.</p>
        <p>Refresh in {{ countdown }} seconds</p>
      </div>
    </div>
    
    <p v-else>Loading job information...</p>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  props: {
    jobId: {
      type: Number,
      required: true
    }
  },
  data() {
    return {
      job: null,
      pollInterval: null,
      countdown: 3
    }
  },
  mounted() {
    this.fetchJob()
    this.startPolling()
  },
  beforeUnmount() {
    clearInterval(this.pollInterval)
  },
  methods: {
    async fetchJob() {
      try {
        const response = await axios.get(`/api/jobs/${this.jobId}`)
        this.job = response.data
      } catch (error) {
        console.error('Error fetching job:', error)
      }
    },
    startPolling() {
      this.pollInterval = setInterval(() => {
        if (this.countdown > 1) {
          this.countdown--
        } else {
          this.countdown = 3
          this.fetchJob()
        }
      }, 1000)
    },
    getVideoUrl(path) {
      if (!path) return ''
      const [bucket, object] = path.split('/', 1)
      return `http://localhost:9000/${bucket}/${object}`
    }
  }
}
</script>