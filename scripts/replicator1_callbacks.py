# replicator1_callbacks


def onRemoveReplicant(replicator, replicant):
	return

def onReplicate(replicator, allOps, newOps, template, master):
	dat = op('table_tilelist')
	sw  = op('switch_tiles')

	# Lookup id -> filePath para manejar gaps (ids no consecutivos)
	id_to_file = {}
	for r in range(1, dat.numRows):
		try:
			id_to_file[int(dat[r, 'id'])] = str(dat[r, 'filePath'])
		except:
			pass

	for tile_op in sorted(allOps, key=lambda o: o.digits):
		row_major_id = tile_op.digits        # id row-major (1-indexed)
		sw_idx       = row_major_id - 1     # input del switch (0-indexed)

		# Asignar archivo correcto por id (no por fila de tabla)
		tile_op.par.file = id_to_file.get(row_major_id, '')

		# Conectar al switch en la posicion row-major correcta
		if sw_idx < len(sw.inputConnectors):
			ic = sw.inputConnectors[sw_idx]
			for conn in list(ic.connections):
				conn.disconnect()
			tile_op.outputConnectors[0].connect(ic)

	return
