import { configureStore } from '@reduxjs/toolkit'
import complaintReducer from './complaintSlice'

export const store = configureStore({
  reducer: {
    complaint: complaintReducer,
  },
  middleware: (getDefault) =>
    // File objects travel through the sendMessage thunk argument, and they are
    // not serialisable. They never enter the store, so the check is narrowed
    // rather than switched off entirely.
    getDefault({
      serializableCheck: {
        ignoredActions: ['complaint/sendMessage/pending'],
        ignoredActionPaths: ['meta.arg.file'],
      },
    }),
})
