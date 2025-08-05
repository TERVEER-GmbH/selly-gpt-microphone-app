import React from 'react'
import styles from './Spinner.module.css'

const Spinner: React.FC = () => (
  <div className={styles.spinner} aria-label="Loading…" />
)

export default Spinner
