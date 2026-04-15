/* Fast dot product and batch scoring for Mnemonic MVP */

/* dot product of two float arrays */
float dot_f32(const float *a, const float *b, int dim) {
    float s = 0.0f;
    for (int i = 0; i < dim; i++) s += a[i] * b[i];
    return s;
}

/* Score a query against N compressed vectors (8-bit codes).
   Returns top_k indices and scores (unsorted).
   alphas[dim], steps[dim]: quantizer state
   codes: N * dim bytes (row-major)
   query: dim floats (normalized)
   out_indices, out_scores: top_k results */
int score_compressed_topk_8bit(
    const float *query, int dim,
    const unsigned char *codes, int n,
    const float *alphas, const float *steps,
    int top_k,
    int *out_indices, float *out_scores
) {
    /* Initialize heap with -inf */
    for (int i = 0; i < top_k; i++) {
        out_scores[i] = -1e30f;
        out_indices[i] = -1;
    }
    int heap_size = 0;

    for (int row = 0; row < n; row++) {
        const unsigned char *code = codes + row * dim;
        float score = 0.0f;
        for (int j = 0; j < dim; j++) {
            score += query[j] * (-alphas[j] + code[j] * steps[j]);
        }

        if (heap_size < top_k) {
            /* Insert into heap */
            out_scores[heap_size] = score;
            out_indices[heap_size] = row;
            heap_size++;
            /* Sift up */
            int c = heap_size - 1;
            while (c > 0) {
                int p = (c - 1) / 2;
                if (out_scores[c] < out_scores[p]) {
                    float ts = out_scores[c]; out_scores[c] = out_scores[p]; out_scores[p] = ts;
                    int ti = out_indices[c]; out_indices[c] = out_indices[p]; out_indices[p] = ti;
                    c = p;
                } else break;
            }
        } else if (score > out_scores[0]) {
            /* Replace min */
            out_scores[0] = score;
            out_indices[0] = row;
            /* Sift down */
            int p = 0;
            while (1) {
                int l = 2*p+1, r = 2*p+2, smallest = p;
                if (l < top_k && out_scores[l] < out_scores[smallest]) smallest = l;
                if (r < top_k && out_scores[r] < out_scores[smallest]) smallest = r;
                if (smallest == p) break;
                float ts = out_scores[p]; out_scores[p] = out_scores[smallest]; out_scores[smallest] = ts;
                int ti = out_indices[p]; out_indices[p] = out_indices[smallest]; out_indices[smallest] = ti;
                p = smallest;
            }
        }
    }
    return heap_size;
}

/* Batch dot products: query (dim,) against matrix (n, dim) -> scores (n,) */
void batch_dot_f32(const float *query, const float *matrix, int n, int dim, float *scores) {
    for (int i = 0; i < n; i++) {
        float s = 0.0f;
        const float *row = matrix + i * dim;
        for (int j = 0; j < dim; j++) s += query[j] * row[j];
        scores[i] = s;
    }
}
